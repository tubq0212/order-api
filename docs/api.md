# 电商订单系统 API 接口文档

## 1. 基本信息

- 服务地址：`http://127.0.0.1:5002`
- 请求格式：需要请求体时使用 `Content-Type: application/json`
- 登录方式：登录成功后使用 HTTP Session Cookie；PowerShell 测试时要复用同一个 `WebRequestSession`
- 响应统一格式：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {}
}
```

常用状态码：`200` 成功，`400` 参数错误，`401` 未登录或登录失败，`403` 无权限，`404` 资源不存在，`409` 业务冲突，`503` 服务异常。

## 2. 健康检查

### `GET /health`

无需登录。用于检查服务和数据库是否可用。

成功示例：

```json
{"code":200,"message":"ok","data":{"service":"order-api","database":"sqlite"}}
```

## 3. 认证与用户

### `POST /auth/setup`

仅系统首次初始化时可用，创建第一个管理员。

请求：

```json
{"username":"admin","password":"Admin@123"}
```

校验：用户名至少 3 位，密码至少 8 位；已经初始化时返回 `409`。

### `POST /auth/login`

请求：

```json
{"username":"admin","password":"Admin@123"}
```

成功后设置登录 Cookie；用户名或密码错误返回 `401`。

### `POST /auth/logout`

需要登录。清除当前 Session。

### `POST /users`

仅管理员可用，创建客户账号，不允许通过此接口创建管理员。

请求：

```json
{"username":"buyer","password":"Buyer@123"}
```

成功返回：

```json
{"user_id":2,"username":"buyer","role":"customer"}
```

重复用户名返回 `409`，弱密码返回 `400`。

## 4. 商品与购物车

### `POST /products`

仅管理员可用。

```json
{"sku":"SKU-001","name":"测试耳机","price":99.9,"stock":5}
```

`price` 和 `stock` 必须为非负数；重复 SKU 返回 `409`。

### `GET /products`

管理员或客户可用。返回所有 active 商品及当前库存。

### `POST /cart/items`

仅客户可用。

```json
{"product_id":1,"quantity":2}
```

数量必须为正整数，加入后购物车中相同商品会累加；超过库存返回 `409`。

### `GET /cart`

仅客户可用。返回当前客户购物车明细。

## 5. 订单

### `POST /orders`

仅客户可用。必须携带 `Idempotency-Key` 请求头，长度不超过 80。

请求：

```json
{"items":[{"product_id":1,"quantity":2}]}
```

创建订单时在事务内校验库存、扣减库存、生成订单明细并清空购物车。相同客户使用相同幂等键重复提交时返回原订单，不重复扣库存。

### `GET /orders`

客户只能查看自己的订单；管理员可查看全部订单。

### `POST /orders/{order_id}/pay`

仅客户可用。待支付订单可模拟支付；重复支付返回 `200`，已支付订单不能重复生成支付记录。

### `POST /orders/{order_id}/cancel`

仅客户可用。待支付订单可取消并恢复库存；已支付订单取消返回 `409`；重复取消返回 `200`。

## 6. 测试重点

接口测试至少覆盖：

1. 未登录访问返回 `401`。
2. 管理员访问客户接口返回 `403`。
3. 重复 SKU、重复用户名返回 `409`。
4. 价格、库存、购买数量的边界和非法值返回 `400`。
5. 库存不足返回 `409` 且数据库库存不变化。
6. 相同幂等键重复下单不重复扣库存。
7. 支付、取消、订单查询的资源归属校验。
8. 并发抢购不会超卖，操作写入 `audit_log`。
