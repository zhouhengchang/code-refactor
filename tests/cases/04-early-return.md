# 测试用例 04 · 嵌套条件提前返回重构

- **用例 ID**：TC-04
- **目标**：验证模型能否把深层嵌套 `if` 改写为卫语句（提前返回），提升可读性且**分支覆盖不变**。
- **语言**：Python

## 输入

`code`：

```python
def calc(o, t, u):
    if o:
        if t:
            if u:
                if u.get("active"):
                    if t.get("limit", 0) > 0:
                        return t["limit"] * u["rate"]
                    else:
                        return 0
                else:
                    return -1
            else:
                return -1
        else:
            return -1
    else:
        return -1
```

`task`：

```
把五层嵌套 if 改为提前返回（卫语句）写法
```

`language`：`python`

## 期望输出

- `ok` 为 `true`
- 嵌套层数由 5 层降为 1 层（连续的 `if not ...: return -1` 卫语句）
- 函数名 `calc` 与三个参数名**保持原样**（未明确要求改名时不改公共接口）
- 返回值集合完全一致：`t["limit"] * u["rate"]`、`0`、`-1`
- 分支覆盖等价

## 验收方法

```python
# 真值表覆盖（伪代码）
assert f({"active": True},  {"limit": 3}, {"rate": 2}) == 6
assert f({"active": True},  {"limit": 0}, {"rate": 2}) == 0
assert f({"active": False}, {"limit": 3}, {"rate": 2}) == -1
assert f({"active": True},  {"limit": 3}, None) == -1
assert f(None, None, None) == -1
```

## 备注

- 这是最基础的重构模式，也最适合用来**判断模型是否可用**：如果连卫语句都改不出来，说明模型太小（0.5B 量级普遍不达标），应换用 6.7B 及以上模型。
- 需注意 `u.get("active")` 与 `t.get("limit", 0)` 的求值顺序，改写后不得提前对 `None` 取值而抛 `AttributeError`。
