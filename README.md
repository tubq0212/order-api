# 电商订单 API

基于 Flask + SQLite 的订单接口项目，覆盖商品、库存、购物车、下单、模拟支付与取消流程，重点验证权限、幂等和库存一致性。

## 本地运行

建议使用 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe app.py
```

服务地址为 http://127.0.0.1:5002。首次运行通过 `POST /auth/setup` 自行创建管理员，再通过 `POST /users` 创建客户。数据库自动建立在 `instance/`，仓库不含实际账号、会话或数据库。

macOS/Linux 可使用 `.venv/bin/python` 执行相同命令。接口及请求示例见 [API 文档](docs/api.md)，完整操作步骤见 [手工测试](docs/testing.md)。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

8 条回归用例覆盖：

- 登录、角色权限及参数校验。
- 重复下单和模拟支付幂等。
- 取消订单恢复库存，已支付订单禁止取消。
- 10 个独立会话抢购 5 件库存：5 次成功、5 次库存不足，最终库存为 0。
- 空 SKU、空商品名的缺陷回归。

测试使用临时数据库。GitHub Actions 在 push 和 pull request 时执行回归。历史性能数据只反映本机开发服务条件，见 [测试记录](docs/test-report.md)。

## 目录

```text
app.py                 路由、权限与订单业务
database.py            SQLite 表结构和连接
tests/                 接口及并发回归
scripts/load_test.py   本地 HTTP 性能检查
docs/                  API、测试步骤与缺陷记录
```

## 范围

支付为状态模拟，不连接支付平台；未实现发货、退款和生产级部署。[BUG-001](docs/bug-001.md) 记录空商品字段问题的复现、修复和回归过程。

真实密钥、Cookie、密码和数据库不要提交。测试代码中的账号密码仅用于临时测试数据；文档中的示例密码不应用于真实部署。服务默认绑定本机地址。
