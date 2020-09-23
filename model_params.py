# -- paths to data
raw_data_paths = {
    'essen': r"D:\Documents\datasets\essen\europa",
    'meertens': r"D:\Documents\datasets\meertens_tune_collection\mtc-fs-1.0.tar\krn"
}
dset_path = r"essen_meertens_songs.hdf5"
beat_multiplier = 48  # duration values will be multiplied by this number and then rounded
test_proportion = 0.1
validate_proportion = 0.1


# -- definition of symbolic music representation
num_dur_vals = 15   # number of duration values
seq_length = 40     # length of song sequences
proportion_for_stats = 1

# -- definition of transformer model structure
nhid = 512          # the dimension of the feedforward network
d_model = 128       # the dimension of the internal transformer representation
nlayers = 2         # number of encoder/decoder layers
nhead = 2           # number of attention heads
dropout = 0.1       # dropout probability

# -- training parameters
num_epochs = 51
val_set_size = 0.1
lr = 0.001
batch_size = 1200
lr_plateau_factor = 0.2
lr_plateau_patience = 3
lr_plateau_threshold = 0.001
clip_gradient_norm = 0.5
save_model_every = 10     # save a new model every X epochs
save_img_every = 4

# -- data augmentation
remove_indices_settings = {'mode': 'center', 'num_indices': 1}

# -- logging
import logging, datetime
start_training_time = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
logging.basicConfig(filename='transformer_train.log', filemode='w', level=logging.INFO,
                    format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
if not any([type(x) is logging.StreamHandler for x in logging.getLogger().handlers]):
    logging.getLogger().addHandler(logging.StreamHandler())
