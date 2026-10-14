# 测试用例 02 · JavaScript 回调地狱改写为 async/await

- **用例 ID**：TC-02
- **目标**：验证模型能否把多层嵌套回调改写为 `async/await`，且**异常处理分支完整保留**。
- **语言**：JavaScript

## 输入

`code`：

```javascript
function loadUserReport(userId, cb) {
  db.query('SELECT * FROM users WHERE id = ?', [userId], function (err, rows) {
    if (err) { return cb(err); }
    if (!rows.length) { return cb(new Error('user not found')); }
    http.get('https://api.example.com/report/' + userId, function (err2, resp) {
      if (err2) { return cb(err2); }
      if (resp.statusCode !== 200) { return cb(new Error('report unavailable')); }
      parse(resp.body, function (err3, data) {
        if (err3) { return cb(err3); }
        cb(null, { user: rows[0], report: data });
      });
    });
  });
}
```

`task`：

```
把嵌套回调改写为 async/await 写法，保留原有的错误处理分支
```

`language`：`javascript`

## 期望输出

- `ok` 为 `true`
- 使用 `async/await` 改写三层嵌套回调
- **四条错误分支全部保留**：
  1. `db.query` 失败
  2. 查询结果为空（`user not found`）
  3. `http.get` 失败
  4. `statusCode !== 200`（`report unavailable`）
  5. `parse` 失败
- 成功路径返回结构与原实现一致：`{ user, report }`
- 使用 `try/catch` 或 `Promise` 链保证错误仍能向外传递

## 验收方法

```javascript
// 错误路径仍能抛出（伪代码）
await assert.rejects(() => loadUserReport(999), /user not found/);
// 成功路径结构不变
const res = await loadUserReport(1);
assert.deepEqual(Object.keys(res), ['user', 'report']);
```

## 备注

- 常见失败模式：模型丢掉 `err2` / `err3` 分支，或把 `parse` 的回调改写时吞掉异常。评审时重点查这三处。
- 若把回调风格的函数签名直接改为 `Promise`，属于**破坏公共接口**，需在输出中显式提示这一改动。
