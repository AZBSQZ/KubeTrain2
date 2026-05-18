#!/usr/bin/env python3
"""测试场景: MNIST手写数字识别 - CNN分类（兼容Agent argparse传参）
数据集格式: mnist_dataset.zip 内含 train.zip/test.zip(PNG图片) + train_labs.txt/test_labs.txt(标签)
"""
import os, sys, argparse, logging, zipfile, io
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from PIL import Image
from torchvision import transforms

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MNISTZipDataset(Dataset):
    """从zip包中读取MNIST PNG图片 + txt标签文件"""
    def __init__(self, zip_path, label_path, transform=None, max_samples=None):
        self.transform = transform or transforms.Compose([
            transforms.Grayscale(num_output_channels=1),
            transforms.Resize((28, 28)),
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,))
        ])
        # 读取标签
        with open(label_path, 'r', encoding='utf-8') as f:
            self.labels = {}
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    self.labels[int(parts[0])] = int(parts[1])

        # 读取zip中的图片文件名
        self.zip_path = zip_path
        self.zf = zipfile.ZipFile(zip_path, 'r')
        self.image_names = sorted([
            n for n in self.zf.namelist()
            if n.lower().endswith(('.png', '.jpg', '.jpeg')) and not n.startswith('__MACOSX')
        ])
        if max_samples and max_samples < len(self.image_names):
            self.image_names = self.image_names[:max_samples]
        logger.info(f"Loaded {len(self.image_names)} images from {zip_path}, {len(self.labels)} labels from {label_path}")

    def __len__(self):
        return len(self.image_names)

    def __getitem__(self, idx):
        name = self.image_names[idx]
        # 从文件名提取索引: "train/123.png" -> 123
        basename = os.path.splitext(os.path.basename(name))[0]
        try:
            img_idx = int(basename)
        except ValueError:
            img_idx = idx
        label = self.labels.get(img_idx, 0)

        img_data = self.zf.read(name)
        img = Image.open(io.BytesIO(img_data)).convert('L')
        if self.transform:
            img = self.transform(img)
        return img, label


class SimpleCNN(nn.Module):
    """简单CNN: 2个卷积层 + 2个全连接层"""
    def __init__(self, num_classes=10):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 7 * 7, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


def find_dataset_files(data_dir):
    """在数据目录中查找zip和标签文件，支持多种解压结构"""
    # 可能的结构:
    # 1) data_dir/train.zip + data_dir/train_labs.txt (直接解压)
    # 2) data_dir/mnist_dataset/train.zip + ... (带子目录)
    candidates = [data_dir]
    for d in os.listdir(data_dir):
        full = os.path.join(data_dir, d)
        if os.path.isdir(full):
            candidates.append(full)

    for base in candidates:
        train_zip = os.path.join(base, 'train.zip')
        test_zip = os.path.join(base, 'test.zip')
        train_labels = os.path.join(base, 'train_labs.txt')
        test_labels = os.path.join(base, 'test_labs.txt')
        if os.path.exists(train_zip) and os.path.exists(train_labels):
            return {
                'train_zip': train_zip,
                'test_zip': test_zip if os.path.exists(test_zip) else None,
                'train_labels': train_labels,
                'test_labels': test_labels if os.path.exists(test_labels) else None,
            }
    return None


def main():
    parser = argparse.ArgumentParser(description='MNIST CNN Training')
    parser.add_argument('--epochs', type=int, default=10, help='Number of training epochs')
    parser.add_argument('--batch-size', type=int, default=64, help='Batch size')
    parser.add_argument('--lr', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--data-dir', type=str, default='./data', help='Dataset directory')
    parser.add_argument('--output-dir', type=str, default='./output', help='Output directory')
    parser.add_argument('--max-samples', type=int, default=None, help='Max training samples (for quick test)')
    args, _ = parser.parse_known_args()

    epochs = args.epochs
    batch_size = args.batch_size
    lr = args.lr
    data_dir = args.data_dir
    output_dir = args.output_dir

    logger.info(f"Config: epochs={epochs}, batch_size={batch_size}, lr={lr}")
    logger.info(f"Data dir: {data_dir}, Output dir: {output_dir}")

    # 查找数据集文件
    files = find_dataset_files(data_dir)
    if not files:
        logger.error(f"Cannot find MNIST dataset files in {data_dir}")
        logger.info(f"Contents of {data_dir}: {os.listdir(data_dir) if os.path.isdir(data_dir) else 'NOT A DIR'}")
        sys.exit(1)

    logger.info(f"Found dataset: train_zip={files['train_zip']}")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Using device: {device}")

    # 加载数据
    transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=1),
        transforms.Resize((28, 28)),
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    train_dataset = MNISTZipDataset(files['train_zip'], files['train_labels'],
                                     transform=transform, max_samples=args.max_samples)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)

    test_loader = None
    if files['test_zip'] and files['test_labels']:
        test_dataset = MNISTZipDataset(files['test_zip'], files['test_labels'],
                                        transform=transform)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    # 模型
    model = SimpleCNN(num_classes=10).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    logger.info(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")
    logger.info(f"Training samples: {len(train_dataset)}")

    # 训练
    best_acc = 0.0
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss, correct, total = 0, 0, 0
        for batch_idx, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * labels.size(0)
            correct += (outputs.argmax(1) == labels).sum().item()
            total += labels.size(0)

        train_loss = total_loss / total
        train_acc = correct / total

        # 测试
        test_acc = 0.0
        if test_loader:
            model.eval()
            test_correct, test_total = 0, 0
            with torch.no_grad():
                for images, labels in test_loader:
                    images, labels = images.to(device), labels.to(device)
                    outputs = model(images)
                    test_correct += (outputs.argmax(1) == labels).sum().item()
                    test_total += labels.size(0)
            test_acc = test_correct / test_total
            if test_acc > best_acc:
                best_acc = test_acc

        logger.info(f'Epoch {epoch}/{epochs} - Loss: {train_loss:.4f}, '
                     f'Train Acc: {train_acc*100:.2f}%, Test Acc: {test_acc*100:.2f}%')

    logger.info(f'Training complete. Best Test Accuracy: {best_acc*100:.2f}%')

    # 保存模型
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, 'mnist_cnn.pth')
    torch.save(model.state_dict(), model_path)
    with open(os.path.join(output_dir, 'results.txt'), 'w') as f:
        f.write(f'best_accuracy={best_acc:.4f}\n')
        f.write(f'final_loss={train_loss:.4f}\n')
        f.write(f'epochs={epochs}\n')
    logger.info(f'Model saved to {model_path}')


if __name__ == '__main__':
    main()
