# 测试用例 01 · Python 函数命名与类型标注重构

- **用例 ID**：TC-01
- **目标**：验证模型能否把单字母命名重构为有意义的命名，并补充类型标注，同时保持逻辑等价。
- **语言**：Python

## 输入

`code`：

```python
def f(a):
    r = []
    for i in a:
        if i % 2 == 0:
            r.append(i * i)
    return r
```

`task`：

```
函数名与变量名改为有意义的命名，补充类型标注与中文注释
```

`language`：`python`

## 期望输出

- `ok` 为 `true`
- `code` 为重构后的完整 Python 代码
- 函数名由 `f` 改为可表达意图的名称（如 `square_even_numbers` / `get_even_squares`）
- 参数 `a`、变量 `r`、`i` 均改为有意义命名
- 补充了类型标注（如 `List[int]` / `Sequence[int]`）与中文注释
- **逻辑等价**：对同一输入，输出列表与原实现完全一致（只保留偶数并求平方，顺序不变）

## 验收方法

```python
# 逻辑等价性校验（伪代码）
assert refactored([1, 2, 3, 4]) == [4, 16]
assert refactored([]) == []
assert refactored([-2, -3]) == [4]
```

## 备注

- 本用例同时约束「不改公共接口」这条硬规则：若原函数已对外暴露 `f`，则必须保留一个同名的兼容包装，或在输出中明确说明改名影响。
