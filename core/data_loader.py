import pickle
from munch import Munch
import numpy as np
import torch
from torch.utils import data


classes = ['IR', 'Ball', 'OR_centred', 'OR_orthogonal', 'OR_opposite']
classes_dict = {i: clss for i, clss in enumerate(classes)}

    
class source_dataset(data.Dataset):
    def __init__(self):

        # Load the dataset
        with open('data/cwru_256_3ch_5cl.pkl', 'rb') as f:
            x, y, k = pickle.load(f)
        
        # Define train dataset
        x_train = x[k < 4]
        y_train = y[k < 4]
        k_train = k[k < 4]

        self.X_train = x_train.astype(np.float32)
        self.y_train = y_train.astype(np.int64)
        self.k_train = k_train.astype(np.int64)

        print(f'X_train shape is {self.X_train.shape}')

        for i in range(len(classes)):
            print(f'Number of {classes_dict[i]} samples: {len(y_train[y_train == i])}')

    def __len__(self):
        return len(self.y_train)
    
    def __getitem__(self, idx):
        return self.X_train[idx], self.y_train[idx], self.k_train[idx]


class reference_dataset(data.Dataset):
    def __init__(self):

        # Load the dataset
        with open('data/cwru_256_3ch_5cl.pkl', 'rb') as f:
            x, y, k = pickle.load(f)
        
        # Define train dataset
        x_train = x[k < 4]
        y_train = y[k < 4]

        self.X_train = x_train.astype(np.float32)
        self.y_train = y_train.astype(np.int64)

        # Prepare pairs
        self.paired_indices = []
        for i in range(len(classes)):
            indices = np.where(y_train == i)[0]
            paired_indices_for_class = []
            for index in indices:
                paired_index = np.random.choice([idx for idx in indices if idx != index])
                paired_indices_for_class.append((index, paired_index))
            self.paired_indices.extend(paired_indices_for_class)

    def __len__(self):
        return len(self.paired_indices)
    
    def __getitem__(self, idx):
        index1, index2 = self.paired_indices[idx]
        return self.X_train[index1], self.X_train[index2], self.y_train[index1]

  
class eval_dataset(data.Dataset):
    def __init__(self, domain=None):

        # Load the dataset
        with open('data/cwru_256_3ch_5cl.pkl', 'rb') as f:
            x, y, k = pickle.load(f)

        with open('data/cwru_256_3ch_5cl_fs.pkl', 'rb') as f:
            fs = pickle.load(f)

        x = x[fs == 0]
        y = y[fs == 0]
        k = k[fs == 0]
        
        # Define train dataset
        if domain is not None:
            x_eval = x[(k >= 4) & (y == domain)]
            y_eval = y[(k >= 4) & (y == domain)]
            k_eval = k[(k >= 4) & (y == domain)]
        else:
            x_eval = x[k >= 4]
            y_eval = y[k >= 4]
            k_eval = k[k >= 4]

        self.X_eval = x_eval.astype(np.float32)
        self.y_eval = y_eval.astype(np.int64)
        self.k_eval = k_eval.astype(np.int64)

        if domain is None:
            print(f'X_eval shape is {self.X_eval.shape}')

            for i in range(len(classes)):
                print(f'Number of {classes_dict[i]} samples: {len(y_eval[y_eval == i])}')

    def __len__(self):
        return len(self.y_eval)
    
    def __getitem__(self, idx):
        return self.X_eval[idx], self.y_eval[idx], self.k_eval[idx]


def get_train_loader(which='source', batch_size=8, num_workers=4, drop_last=False):

    if which == 'source':
        dataset = source_dataset()
    elif which == 'reference':
        dataset = reference_dataset()
    else:
        raise NotImplementedError
    
    dataloader = data.DataLoader(dataset=dataset,
                                batch_size=batch_size,
                                shuffle=True,
                                num_workers=num_workers,
                                pin_memory=True,
                                drop_last=drop_last)
    
    print(f'Number of {which} batches: {len(dataloader)}')

    return dataloader


def get_eval_loader(batch_size=32, num_workers=4, domain=None, drop_last=False):
    
    dataloader = data.DataLoader(dataset=eval_dataset(domain),
                                batch_size=batch_size,
                                shuffle=True,
                                num_workers=num_workers,
                                pin_memory=True,
                                drop_last=drop_last)

    return dataloader


class InputFetcher:
    def __init__(self, loader, loader_ref=None, latent_dim=16, mode=''):
        self.loader = loader
        self.loader_ref = loader_ref
        self.latent_dim = latent_dim
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.mode = mode

    def _fetch_inputs(self):
        try:
            x, y, k = next(self.iter)
        except (AttributeError, StopIteration):
            self.iter = iter(self.loader)
            x, y, k = next(self.iter)
        return x, y, k

    def _fetch_refs(self):
        try:
            x, x2, y = next(self.iter_ref)
        except (AttributeError, StopIteration):
            self.iter_ref = iter(self.loader_ref)
            x, x2, y = next(self.iter_ref)
        return x, x2, y

    def __next__(self):
        x, y, k = self._fetch_inputs()
        if self.mode == 'train':
            x_ref, x_ref2, y_ref = self._fetch_refs()
            z_trg = torch.randn(x.size(0), self.latent_dim)
            z_trg2 = torch.randn(x.size(0), self.latent_dim)
            inputs = Munch(x_src=x, y_src=y, k_src=k, y_ref=y_ref,
                           x_ref=x_ref, x_ref2=x_ref2,
                           z_trg=z_trg, z_trg2=z_trg2)
        elif self.mode == 'val':
            x_ref, y_ref, k_ref = self._fetch_inputs()
            inputs = Munch(x_src=x, y_src=y, k_src=k,
                           x_ref=x_ref, y_ref=y_ref, k_ref=k_ref)
        elif self.mode == 'test':
            inputs = Munch(x=x, y=y, k=k)
        else:
            raise NotImplementedError

        return Munch({k: v.to(self.device)
                      for k, v in inputs.items()})
    