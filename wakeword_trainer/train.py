"""Train the wake-word head and export it as ONNX [1,16,96] -> [1,1] (openWakeWord compatible)."""
import json
import os
import pickle
import random
import time

import numpy as np
import torch
import torch.nn as nn

from . import EMBED_DIM, WINDOW, features as F


class Head(nn.Module):
    """Flatten -> (Linear-LayerNorm-ReLU) x2 -> Linear -> sigmoid: the openWakeWord 'dnn' head."""

    def __init__(self, hidden=32):
        super().__init__()
        self.fc1 = nn.Linear(WINDOW * EMBED_DIM, hidden); self.ln1 = nn.LayerNorm(hidden)
        self.fc2 = nn.Linear(hidden, hidden); self.ln2 = nn.LayerNorm(hidden)
        self.fc3 = nn.Linear(hidden, 1)
        self.drop = nn.Dropout(0.1)

    def forward(self, x):
        x = x.reshape(x.shape[0], -1)
        x = self.drop(torch.relu(self.ln1(self.fc1(x))))
        x = self.drop(torch.relu(self.ln2(self.fc2(x))))
        return torch.sigmoid(self.fc3(x))


def build_features(ws, log=print, rebuild=False):
    if os.path.exists(ws.cache) and not rebuild:
        with open(ws.cache, 'rb') as f:
            return pickle.load(f)
    files = F.split_files(ws)
    ambient = F.load_ambient(ws)
    log(f"extracting audio features ({len(files['train_pos'])} synthetic + {len(files['train_real_pos'])} "
        f"recorded positives, {len(files['train_neg'])} + {len(files['train_real_neg'])} negatives)")
    t0 = time.time()
    data = {
        'train': F.build(files['train_pos'] + files['train_real_pos'] * 6,
                         files['train_neg'] + files['train_real_neg'] * 2, ambient),
        'hold': F.build(files['hold_pos'], files['hold_neg'], ambient, n_aug_pos=2, n_aug_neg=1),
    }
    log(f'features ready in {time.time() - t0:.0f}s')
    with open(ws.cache, 'wb') as f:
        pickle.dump(data, f)
    return data


def export_onnx(model, path):
    model.eval()
    dummy = torch.zeros(1, WINDOW, EMBED_DIM)
    kwargs = dict(input_names=['t0'], output_names=['out'], opset_version=17)
    try:
        torch.onnx.export(model, dummy, path, dynamo=False, **kwargs)
    except TypeError:                       # older PyTorch without the dynamo switch
        torch.onnx.export(model, dummy, path, **kwargs)


def train(ws, epochs=40, hidden=32, progress=None, log=print, rebuild=False, seed=0):
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    data = build_features(ws, log, rebuild)
    Xp, Xn = data['train']
    Xp_h, Xn_h = data['hold']
    if len(Xp) == 0 or len(Xn) == 0:
        raise RuntimeError('no training windows: generate the synthetic voices first')
    log(f'training windows: {len(Xp)} positive, {len(Xn)} negative')

    model = Head(hidden)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-3)
    X = np.concatenate([Xp, Xn])
    y = np.concatenate([np.ones(len(Xp)), np.zeros(len(Xn))]).astype(np.float32)
    hard = None
    history = []
    for epoch in range(epochs):
        idx = np.random.permutation(len(X))
        if hard is not None and len(hard):               # hard-negative mining: replay the worst ones
            idx = np.concatenate([idx, np.repeat(hard, 3)])
            np.random.shuffle(idx)
        total = 0.0
        for i in range(0, len(idx), 256):
            b = idx[i:i + 256]
            xb, yb = torch.from_numpy(X[b]), torch.from_numpy(y[b]).unsqueeze(1)
            weight = torch.where(yb > 0.5, torch.tensor(2.0), torch.tensor(1.0))
            loss = (nn.functional.binary_cross_entropy(model(xb), yb, reduction='none') * weight).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            total += loss.item() * len(b)
        if epoch % 5 == 4 or epoch == epochs - 1:
            model.eval()
            with torch.no_grad():
                s = model(torch.from_numpy(X)).numpy().ravel()
                rec = float((model(torch.from_numpy(Xp_h)).numpy() > 0.5).mean()) if len(Xp_h) else float('nan')
                fpr = float((model(torch.from_numpy(Xn_h)).numpy() > 0.5).mean()) if len(Xn_h) else float('nan')
            model.train()
            hard = np.where((y == 0) & (s > 0.3))[0]
            history.append({'epoch': epoch + 1, 'loss': total / len(idx), 'holdout_recall': rec,
                            'holdout_false_window_rate': fpr})
            log(f'epoch {epoch + 1}/{epochs}  loss={total / len(idx):.4f}  holdout recall={rec:.3f}  '
                f'false windows={fpr:.4f}')
        if progress:
            progress(epoch + 1, epochs)

    os.makedirs(ws.out, exist_ok=True)
    export_onnx(model, ws.model_path)
    with open(os.path.join(ws.out, 'training.json'), 'w', encoding='utf-8') as f:
        json.dump({'history': history, 'epochs': epochs, 'hidden': hidden}, f, indent=2)
    log(f'model saved: {ws.model_path}')
    return {'model': ws.model_path, 'history': history}
