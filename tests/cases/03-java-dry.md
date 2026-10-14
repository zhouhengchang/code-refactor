# 测试用例 03 · Java 重复逻辑提取

- **用例 ID**：TC-03
- **目标**：验证模型能否识别三处重复校验逻辑并提取为私有方法，且**行为完全不变**。
- **语言**：Java

## 输入

`code`：

```java
public class OrderService {

    public void createOrder(Order order) {
        if (order == null) {
            throw new IllegalArgumentException("order 不能为空");
        }
        if (order.getId() == null || order.getId().trim().isEmpty()) {
            throw new IllegalArgumentException("order.id 不能为空");
        }
        if (order.getAmount() == null || order.getAmount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("order.amount 必须大于 0");
        }
        // ... 创建订单
    }

    public void updateOrder(Order order) {
        if (order == null) {
            throw new IllegalArgumentException("order 不能为空");
        }
        if (order.getId() == null || order.getId().trim().isEmpty()) {
            throw new IllegalArgumentException("order.id 不能为空");
        }
        // ... 更新订单
    }

    public void cancelOrder(Order order) {
        if (order == null) {
            throw new IllegalArgumentException("order 不能为空");
        }
        if (order.getId() == null || order.getId().trim().isEmpty()) {
            throw new IllegalArgumentException("order.id 不能为空");
        }
        // ... 取消订单
    }
}
```

`task`：

```
把三个方法中重复的参数校验逻辑提取为私有工具方法，消除重复代码，保持行为完全不变
```

`language`：`java`

## 期望输出

- `ok` 为 `true`
- 提取出私有方法（如 `validateOrder` / `requireNonEmpty`）
- 三个公开方法（`createOrder` / `updateOrder` / `cancelOrder`）**签名不变**
- 校验顺序不变，抛出的异常类型（`IllegalArgumentException`）与**错误文案逐字一致**
- `createOrder` 独有的金额校验保留

## 验收方法

```java
// 异常文案必须逐字一致
assertThrows(IllegalArgumentException.class, () -> svc.updateOrder(null));
// 期望 message 等于 "order 不能为空"
```

## 备注

- 关键风险：模型合并校验时**改动错误文案**或**调换校验顺序**。文案与顺序都属于可观测行为，必须保持。
- 若提取后的方法命名不符合项目约定，可接受，但不能因此改变异常行为。
