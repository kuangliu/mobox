import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.backends.cudnn as cudnn

import mobox.utils.checkpoint as cu
import mobox.utils.distributed as du
import mobox.utils.multiprocessing as mp
import mobox.models.optimizer as optim

from projects.wayformer.model import Wayformer
from projects.wayformer.dataset import WaymoDataset

from config.defaults import get_cfg
from mobox.models import build_model
from mobox.utils.logger import Logger
from mobox.datasets import construct_loader, shuffle_dataset


log = Logger()


def train_epoch(train_loader, model, optimizer, epoch, cfg):
    """Epoch training.
    Args:
      train_loader (DataLoader): training data loader.
      model (model): the video model to train.
      optimizer (optim): the optimizer to perform optimization on the model's parameters.
      epoch (int): current epoch of training.
      cfg (CfgNode): configs. Details can be found in config/defaults.py
    """
    if du.is_master_proc():
        log.info(f'Epoch: {epoch}')

    model.train()
    num_batches = len(train_loader)
    train_loss = 0.0
    for batch_idx, inputs in enumerate(train_loader):
        # inputs, labels = inputs.cuda(non_blocking=True), labels.cuda()

        # Update lr.
        lr = optim.get_epoch_lr(epoch + float(batch_idx) / num_batches, cfg)
        optim.set_lr(optimizer, lr)

        # Forward.
        loss = model(inputs)

        # Backward.
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # Gather all predictions across all devices.
        if cfg.NUM_GPUS > 1:
            loss = du.all_reduce([loss])[0]

        if du.is_master_proc():
            train_loss += loss.item()
            log.info(f"Loss: {train_loss/(batch_idx+1):.3f} | LR: {lr:.5f}")
            log.add_scalar("train_loss", train_loss/(batch_idx+1), batch_idx)


def train(cfg):
    train_loader = construct_loader(cfg, mode="train")
    # val_loader = construct_loader(cfg, mode="val")
    model = build_model(cfg)
    optimizer = optim.construct_optimizer(model, cfg)

    for epoch in range(cfg.SOLVER.MAX_EPOCH):
        shuffle_dataset(train_loader, epoch)
        train_epoch(train_loader, model, optimizer, epoch, cfg)
        # eval_epoch(val_loader, model, epoch, cfg)
        # cu.save_checkpoint(model, optimizer, epoch, cfg)


if __name__ == "__main__":
    import os
    torch.multiprocessing.set_start_method("spawn")
    cfg = get_cfg()
    if cfg.NUM_GPUS > 1:
        shard_id = int(os.getenv("RANK", default=0))
        num_shards = int(os.getenv("WORLD_SIZE", default=1))

        torch.multiprocessing.spawn(
            mp.run,
            nprocs=cfg.NUM_GPUS,
            args=(
                cfg.NUM_GPUS,
                train,
                # "file:///dataset/liuk6_sharedfile",
                "tcp://localhost:9999",
                shard_id,
                num_shards,
                'nccl',
                cfg,
            ),
            daemon=False,
        )
    else:
        train(cfg)
