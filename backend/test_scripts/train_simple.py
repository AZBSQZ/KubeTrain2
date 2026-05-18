"""
KubeTrain2 测试训练脚本 - 纯CPU，无外部依赖
模拟一个简单的线性回归训练过程，输出标准格式的 Epoch/Loss/Accuracy 日志
"""
import argparse
import json
import math
import os
import random
import time


def generate_data(n=200):
    """生成简单的线性回归数据: y = 2x + 1 + noise"""
    X = [random.uniform(-5, 5) for _ in range(n)]
    Y = [2 * x + 1 + random.gauss(0, 0.5) for x in X]
    return X, Y


def train(epochs=5, lr=0.01, data_size=200):
    """简单的梯度下降线性回归"""
    random.seed(42)
    X, Y = generate_data(data_size)

    # 初始化参数
    w = random.uniform(-1, 1)
    b = random.uniform(-1, 1)

    n = len(X)
    history = {'train_loss': [], 'train_accuracy': [], 'epochs': []}

    print(f"[Training] Starting training: {epochs} epochs, lr={lr}, data_size={data_size}")
    print(f"[Training] Initial params: w={w:.4f}, b={b:.4f}")
    print(f"[Training] Target: w=2.0, b=1.0")
    print()

    for epoch in range(1, epochs + 1):
        # Forward pass
        total_loss = 0
        correct = 0
        for i in range(n):
            pred = w * X[i] + b
            loss = (pred - Y[i]) ** 2
            total_loss += loss
            # "Accuracy": prediction within 1.0 of target
            if abs(pred - Y[i]) < 1.0:
                correct += 1

        avg_loss = total_loss / n
        accuracy = correct / n * 100  # percentage

        # Backward pass (gradient descent)
        dw = 0
        db = 0
        for i in range(n):
            pred = w * X[i] + b
            dw += 2 * (pred - Y[i]) * X[i] / n
            db += 2 * (pred - Y[i]) / n
        w -= lr * dw
        b -= lr * db

        history['train_loss'].append(round(avg_loss, 4))
        history['train_accuracy'].append(round(accuracy, 2))
        history['epochs'].append(epoch)

        print(f"Epoch {epoch}/{epochs} - Loss: {avg_loss:.4f} - Accuracy: {accuracy:.2f}% - w={w:.4f}, b={b:.4f}")

        # 模拟训练耗时
        time.sleep(1)

    print()
    print(f"[Training] Training completed!")
    print(f"[Training] Final params: w={w:.4f}, b={b:.4f}")
    print(f"[Training] Final Loss: {history['train_loss'][-1]:.4f}")
    print(f"[Training] Final Accuracy: {history['train_accuracy'][-1]:.2f}%")

    return w, b, history


def main():
    parser = argparse.ArgumentParser(description='Simple Linear Regression Training')
    parser.add_argument('--epochs', type=int, default=5, help='Number of training epochs')
    parser.add_argument('--lr', type=float, default=0.01, help='Learning rate')
    parser.add_argument('--data-size', type=int, default=200, help='Training data size')
    parser.add_argument('--data-dir', type=str, default='', help='Dataset directory (unused)')
    parser.add_argument('--output-dir', type=str, default='', help='Output directory')
    args, _ = parser.parse_known_args()

    output_dir = args.output_dir or os.environ.get('OUTPUT_PATH', '')

    w, b, history = train(epochs=args.epochs, lr=args.lr, data_size=args.data_size)

    # 保存模型和指标
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

        # 保存模型参数
        model_path = os.path.join(output_dir, 'model.json')
        with open(model_path, 'w') as f:
            json.dump({'w': w, 'b': b}, f, indent=2)
        print(f"[Training] Model saved to {model_path}")

        # 保存训练指标
        metrics_path = os.path.join(output_dir, 'metrics.json')
        with open(metrics_path, 'w') as f:
            json.dump(history, f, indent=2)
        print(f"[Training] Metrics saved to {metrics_path}")


if __name__ == '__main__':
    main()
