"""Torch-dependent state and health diagnostics, shared with CPU smoke tests."""
import random
import numpy as np
import torch


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def rng_state():
    state = {'python': random.getstate(), 'numpy': np.random.get_state(), 'torch': torch.get_rng_state()}
    if torch.cuda.is_available():
        state['cuda'] = torch.cuda.get_rng_state_all()
    if torch.backends.mps.is_available():
        state['mps'] = torch.mps.get_rng_state()
    return state


def restore_rng(state):
    random.setstate(state['python'])
    np.random.set_state(state['numpy'])
    torch.set_rng_state(state['torch'].cpu())
    if 'cuda' in state:
        torch.cuda.set_rng_state_all([x.cpu() for x in state['cuda']])
    if 'mps' in state:
        torch.mps.set_rng_state(state['mps'].cpu())


def save_state(path, model, optimizer, **extra):
    from pathlib import Path
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    torch.save({'schema': 2, 'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                'rng': rng_state(), **extra}, tmp)
    tmp.replace(path)


def restore_matching(path, model, optimizer, restore_random=False):
    blob = torch.load(path, weights_only=False, map_location='cpu')
    if blob.get('schema') != 2:
        raise ValueError('Legacy resume lacks reproducible state; use its weights as --init in a new run')
    model.load_state_dict(blob['model'])
    optimizer.load_state_dict(blob['optimizer'])
    if restore_random:
        restore_rng(blob['rng'])
    return blob


def gradient_norm(parameters):
    squares = [p.grad.detach().float().square().sum() for p in parameters if p.grad is not None]
    return float(torch.stack(squares).sum().sqrt()) if squares else 0.0


class Exposure:
    def __init__(self, state=None):
        self.sources = (state or {}).get('sources', {})
        self.seen = {k: set(v) for k,v in (state or {}).get('seen', {}).items()}

    def add(self, metadata, lengths, losses, batch_stats):
        for source, counts in batch_stats['sources'].items():
            row = self.sources.setdefault(source, dict(items=0, seconds=0.0, loss_sum=0.0,
                 requested=0, ctc_dropped=0, bucket_dropped=0, repeated=0))
            for key, value in counts.items():
                row[key] += value
        for m, length, loss in zip(metadata, lengths, losses):
            row = self.sources[m['source']]
            row['items'] += 1
            row['seconds'] += float(length)*0.01
            row['loss_sum'] += float(loss)
            self.seen.setdefault(m['source'], set()).add(m['id'])

    def report(self):
        total = sum(r['items'] for r in self.sources.values())
        return {k: {**r, 'unique_items': len(self.seen.get(k, [])),
                    'mean_loss': r['loss_sum']/r['items'] if r['items'] else None,
                    'item_share': r['items']/total if total else 0.0} for k,r in self.sources.items()}

    def state(self):
        return {'sources': self.sources, 'seen': {k: sorted(v) for k,v in self.seen.items()}}
