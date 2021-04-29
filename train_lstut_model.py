import time
import numpy as np
import torch
import torch.nn as nn
# import point_set_dataloader as dl
import toy_datasets as td
import test_trained_notetuple_model as ttnm
import models.LSTUT_model as lstut
import training_helper_functions as tr_funcs
from torch.utils.data import DataLoader
import plot_outputs as po
import model_params
import logging
import argparse

from importlib import reload
reload(tr_funcs)
reload(ttnm)
reload(td)
reload(lstut)
reload(model_params)
reload(po)

parser = argparse.ArgumentParser(description='Training script, with optional parameter searching.')
parser.add_argument('parameters', default='default_params.json',
                    help='Parameter file in .json format.')
parser.add_argument('-m', '--mod_number', type=int, default=0,
                    help='Index of specific modification to apply to given parameter set.')
parser.add_argument('-l', '--logging', action='store_true',
                    help='Whether or not to log training results to file.')
args = vars(parser.parse_args())

params = model_params.Params(args['parameters'],  args['logging'], args['mod_number'])

assert 1 == 4

device, num_gpus = tr_funcs.get_cuda_info()
logging.info('defining datasets...')
# dset_tr = dl.MidiNoteTupleDataset(
#     dset_fname=params.dset_path,
#     seq_length=params.seq_length,
#     base='train',
#     num_feats=params.num_feats,
#     padding_amt=params.padding_amt,
#     dataset_proportion=params.dataset_proportion,
# )
# dset_vl = dl.MidiNoteTupleDataset(
#     dset_fname=params.dset_path,
#     seq_length=params.seq_length,
#     base='validate',
#     num_feats=params.num_feats,
#     padding_amt=params.padding_amt,
#     dataset_proportion=params.dataset_proportion,
#     use_stats_from=dset_tr)

dset_args = {
    'num_feats': params.num_feats,
    'seq_length': params.seq_length,
    'seq_period': params.seq_length // 5
}
dset_args.update(params.toy_dataset_args)

dset_tr = td.SequenceCopyDataset(**dset_args)
dset_args['num_seqs'] = dset_args['num_seqs'] // 5
dset_vl = td.SequenceCopyDataset(**dset_args)

dloader = DataLoader(dset_tr, params.batch_size, pin_memory=True)
dloader_val = DataLoader(dset_vl, params.batch_size, pin_memory=True)
num_feats = dset_tr.num_feats

model = lstut.LSTUT(**params.lstut_settings).to(device)
model = nn.DataParallel(model, device_ids=list(range(num_gpus)))
model_size = sum(p.numel() for p in model.parameters())
logging.info(f'created model with n_params={model_size}')

optimizer = torch.optim.Adam(model.parameters(), lr=params.lr)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer=optimizer, **params.scheduler_settings)

class_ratio = params.seq_length // sum(list(params.error_indices_settings.values()))
criterion = torch.nn.BCEWithLogitsLoss(reduction='sum', pos_weight=torch.tensor(class_ratio))

logging.info('beginning training')
start_time = time.time()
val_losses = []
best_model = None
tr_funcs.log_gpu_info()
for epoch in range(params.num_epochs):
    epoch_start_time = time.time()

    # perform training epoch
    model.train()
    train_loss, tr_exs = tr_funcs.run_epoch(
        model=model,
        dloader=dloader,
        optimizer=optimizer,
        criterion=criterion,
        device=device,
        make_examples_settings=params.error_indices_settings,
        train=True,
        log_each_batch=True
    )

    # test on validation set
    model.eval()
    num_entries = 0
    val_loss = 0.
    with torch.no_grad():
        val_loss, val_exs = tr_funcs.run_epoch(
            model=model,
            dloader=dloader_val,
            optimizer=optimizer,
            criterion=criterion,
            device=device,
            make_examples_settings=params.error_indices_settings,
            train=False,
            log_each_batch=False
        )

    val_losses.append(val_loss)
    scheduler.step(val_loss)
    tr_funcs.log_gpu_info()

    tr_f1, tr_thresh = ttnm.multilabel_thresholding(tr_exs['output'], tr_exs['target'])
    val_f1 = ttnm.f_measure(val_exs['output'].cpu(), val_exs['target'].cpu(), tr_thresh)

    epoch_end_time = time.time()
    logging.info(
        f'epoch {epoch:3d} | '
        f's/epoch    {(epoch_end_time - epoch_start_time):3.5f} | '
        f'train_loss {train_loss:1.6f} | '
        f'val_loss   {val_loss:1.6f} |\n'
        f'          | '
        f'tr_thresh  {tr_thresh:1.5f} | '
        f'tr_f1      {tr_f1:1.6f} | '
        f'val_f1     {val_f1:1.6f} | '
    )

    # save an image
    if not epoch % params.save_img_every and epoch > 0:
        img_fpath = f'./out_imgs/epoch_{epoch}_{params.params_id_str}.png'
        tr_funcs.save_img(tr_exs, img_fpath)

    # save a model checkpoint
    # if (not epoch % params.save_model_every) and epoch > 0 and params.save_model_every > 0:
    #     m_name = (
    #         f'lstut_{params.start_training_time}'
    #         f'_{params.lstut_summary_str}.pt')
    #     torch.save(cur_model, m_name)

    # # keep snapshot of best model
    # cur_model = {
    #         'epoch': epoch,
    #         'model_state_dict': model.state_dict(),
    #         'optimizer_state_dict': optimizer.state_dict(),
    #         'scheduler_state_dict': scheduler.state_dict(),
    #         'val_losses': val_losses,
    #         }
    # if len(val_losses) == 1 or val_losses[-1] < min(val_losses[:-1]):
    #     best_model = copy.deepcopy(cur_model)

    # early stopping
    time_since_best = epoch - val_losses.index(min(val_losses))
    if time_since_best > params.early_stopping_patience:
        logging.info(f'stopping early at epoch {epoch} because validation score stopped increasing')
        break

    elapsed = time.time() - start_time
    if elapsed > (params.max_time_minutes * 60):
        logging.info(f'stopping early at epoch {epoch} because of time limit')
        break

logging.info(f'Training over at epoch at epoch {epoch}.')

for i in range(3):
    img_fpath = f'./out_imgs/FINAL_{i}_{params.params_id_str}.png'
    tr_funcs.save_img(tr_exs, img_fpath)

# # if max_epochs reached, or early stopping condition reached, save best model
# best_epoch = best_model['epoch']
# m_name = (f'lstut_best_{params.start_training_time}_{params.lstut_summary_str}.pt')
# torch.save(best_model, m_name)