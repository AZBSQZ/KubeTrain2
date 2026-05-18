#!/usr/bin/env python3
"""测试场景3: TXT文本分类 - 情感分析（词袋+MLP）"""
import os, sys, argparse, logging, collections
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SentimentDataset(Dataset):
    def __init__(self, txt_path, vocab_size=500):
        labels, texts = [], []
        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or '\t' not in line:
                    continue
                parts = line.split('\t', 1)
                labels.append(int(parts[0]))
                texts.append(parts[1].lower().split())

        # 构建词表
        counter = collections.Counter(w for t in texts for w in t)
        self.vocab = {w: i+1 for i, (w, _) in enumerate(counter.most_common(vocab_size))}
        self.vocab_size = vocab_size + 1

        # 转为词袋向量
        self.X = torch.zeros(len(texts), self.vocab_size, dtype=torch.float32)
        for i, words in enumerate(texts):
            for w in words:
                idx = self.vocab.get(w, 0)
                self.X[i, idx] += 1
        self.y = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

class TextMLP(nn.Module):
    def __init__(self, vocab_size, hidden_dim=64, num_classes=2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(vocab_size, hidden_dim), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(hidden_dim, num_classes)
        )
    def forward(self, x):
        return self.net(x)

def find_txt(data_dir):
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            if f.endswith('.txt'):
                return os.path.join(root, f)
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default=os.environ.get('DATASET_PATH', '/data/dataset'))
    parser.add_argument('--output-dir', default=os.environ.get('OUTPUT_PATH', '/data/output'))
    parser.add_argument('--epochs', type=int, default=15)
    parser.add_argument('--num_epochs', type=int, default=None)
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument('--lr', type=float, default=0.005)
    parser.add_argument('--learning_rate', type=float, default=None)
    args, _ = parser.parse_known_args()

    epochs = args.num_epochs or args.epochs
    lr = args.learning_rate or args.lr

    txt_path = find_txt(args.data_dir)
    if not txt_path:
        logger.error(f'No TXT file found in {args.data_dir}')
        sys.exit(1)
    logger.info(f'Using TXT: {txt_path}')

    dataset = SentimentDataset(txt_path)
    train_size = int(0.8 * len(dataset))
    test_size = len(dataset) - train_size
    train_ds, test_ds = random_split(dataset, [train_size, test_size])

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size)

    model = TextMLP(dataset.vocab_size)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    logger.info(f'Dataset: {len(dataset)} samples, Vocab: {dataset.vocab_size}')
    logger.info(f'Epochs: {epochs}, LR: {lr}')

    best_acc = 0
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss, correct, total = 0, 0, 0
        for X, y in train_loader:
            optimizer.zero_grad()
            out = model(X)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * y.size(0)
            correct += (out.argmax(1) == y).sum().item()
            total += y.size(0)

        model.eval()
        test_correct, test_total = 0, 0
        with torch.no_grad():
            for X, y in test_loader:
                out = model(X)
                test_correct += (out.argmax(1) == y).sum().item()
                test_total += y.size(0)
        test_acc = test_correct / test_total
        if test_acc > best_acc:
            best_acc = test_acc

        logger.info(f'Epoch {epoch}/{epochs} - Loss: {total_loss/total:.4f}, '
                     f'Train Acc: {correct/total*100:.2f}%, Test Acc: {test_acc*100:.2f}%')

    logger.info(f'Training complete. Best Test Accuracy: {best_acc*100:.2f}%')

    os.makedirs(args.output_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(args.output_dir, 'model.pth'))

if __name__ == '__main__':
    main()
