# 电商订单系统手动测试教程

## 1. 环境准备

在 PowerShell 中执行：

```powershell
cd order-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

如果 PowerShell 禁止执行脚本，可直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 2. 启动服务

```powershell
python app.py
```

服务地址为 `http://127.0.0.1:5002`。另开一个 PowerShell 窗口执行测试请求。

## 3. 手动冒烟测试

下面命令使用 PowerShell 的 `Invoke-RestMethod`，每一步都检查返回的 `code`。

### 3.1 健康检查

```powershell
irm http://127.0.0.1:5002/health
```

预期：HTTP 200，`code=200`，`data.service=order-api`。

### 3.2 初始化管理员并登录

```powershell
$base = 'http://127.0.0.1:5002'
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = @{username='admin'; password='Admin@123'} | ConvertTo-Json
irm "$base/auth/setup" -Method Post -ContentType 'application/json' -Body $body -WebSession $session
irm "$base/auth/login" -Method Post -ContentType 'application/json' -Body $body -WebSession $session
```

预期：首次初始化和登录均返回 200；再次调用 setup 应返回 409。

### 3.3 创建商品并查询

```powershell
$product = @{sku='SKU-001'; name='测试耳机'; price=99.9; stock=5} | ConvertTo-Json
irm "$base/products" -Method Post -ContentType 'application/json' -Body $product -WebSession $session
irm "$base/products" -WebSession $session
```

预期：创建返回商品 ID；重复使用相同 SKU 返回 409；商品列表显示库存 5。

### 3.4 创建客户并登录

管理员登录后通过接口创建客户账号：

```powershell
$customerBody = @{username='buyer'; password='Buyer@123'} | ConvertTo-Json
irm "$base/users" -Method Post -ContentType 'application/json' -Body $customerBody -WebSession $session
```

预期：返回 200 和客户 `user_id`；重复用户名返回 409；短密码返回 400。

然后使用新会话登录：

```powershell
$customer = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = @{username='buyer'; password='Buyer@123'} | ConvertTo-Json
irm "$base/auth/login" -Method Post -ContentType 'application/json' -Body $login -WebSession $customer
```

### 3.5 下单、支付、取消

假设商品 ID 为 1：

```powershell
$order = @{items=@(@{product_id=1; quantity=2})} | ConvertTo-Json -Depth 4
irm "$base/orders" -Method Post -ContentType 'application/json' -Headers @{'Idempotency-Key'='demo-001'} -Body $order -WebSession $customer
irm "$base/orders/1/pay" -Method Post -WebSession $customer
irm "$base/orders" -WebSession $customer
```

预期：下单后库存从 5 变 3；支付后状态为 `paid`；重复支付仍返回 200 且不会生成第二笔支付。

重新创建一个待支付订单后执行：

```powershell
irm "$base/orders/2/cancel" -Method Post -WebSession $customer
```

预期：状态为 `cancelled`，库存恢复；已支付订单取消返回 409。

### 3.6 并发下单一致性测试

自动化测试会创建 10 个独立会话，同时抢购 5 件库存：

```powershell
python -m pytest tests/test_concurrency.py -vv
```

预期：5 个请求返回 200，5 个请求返回 409，最终库存为 0。这个用例验证的是事务和库存一致性，不等同于生产环境容量压测；正式压测还需要记录并发数、响应时间、吞吐量、错误率和服务资源使用率。

### 3.7 真实服务进程压测

先在一个 PowerShell 窗口启动服务：

```powershell
python app.py
```

再打开另一个窗口执行：

```powershell
python scripts/load_test.py --requests 100 --concurrency 10
```

脚本默认请求 `/health`，会输出 JSON 格式的成功率、状态码分布、吞吐量、平均耗时、P50、P95 和最大耗时。交付测试报告时，应保存命令、完整输出、机器配置和测试时间；不要把开发机结果直接表述为生产容量上限。

## 4. 异常与安全用例

| 用例 | 操作 | 预期 |
|---|---|---|
| 未登录访问 | 直接 GET `/products` | 401 |
| 越权 | 管理员 POST `/cart/items` | 403 |
| 非法数量 | 下单 quantity=0 或负数 | 400 |
| 库存不足 | quantity 大于库存 | 409，库存不变 |
| 幂等 | 相同 `Idempotency-Key` 重复下单 | 返回同一订单，不重复扣库存 |
| 不存在订单 | 支付或取消不存在 ID | 404 |
| 并发抢购 | 10 个请求同时购买 5 件库存 | 5 个 200、5 个 409，库存为 0 |

## 5. 自动化回归与交付记录

```powershell
python -m pytest
```

通过标准：所有用例通过，输出 `X passed`。记录日期、Python 版本、测试命令、通过数、失败数和缺陷编号；不要只截图接口成功，要同时核对数据库中的库存、订单状态、支付记录和 `audit_log`。
