import h5py
import numpy as np
import data_augmentation.needleman_wunsch_alignment as align
from numba import njit
from collections import Counter
import error_gen_logistic_regression as elgr

dset_path = r'./quartets_felix_omr.h5'
ngram = 5 # n for n-grams for maxent markov model

# voice, onset, time_to_next_onset, duration, midi_pitch, notated_pitch, accidental
# here we take only voice, time to next onset, duration, midi pitch
inds_subset = np.array([0, 2, 3, 4])

with h5py.File(dset_path, 'a') as f:
    correct_fnames = [x for x in f.keys() if 'aligned' in x and 'op80' not in x]
    error_fnames = [x for x in f.keys() if 'omr' in x]
    correct_dset = [f[x][:, inds_subset] for x in correct_fnames]
    error_dset = [f[x][:, inds_subset] for x in error_fnames]

error_notes = {x:[] for x in ['replace_mod', 'insert_mod']}
correct_seqs_all = []
all_align_records = []

# training samples for logistic regression (MaxEnt Markov Model) for creating errors
# features in X are: [ngram of past 3 classes || note vector]
X = []
Y = []
for ind in range(len(correct_dset)):
        
    print(f'aligning {correct_fnames[ind]}...' )
    correct_seq = [x for x in correct_dset[ind]]
    error_seq = [x for x in error_dset[ind]]
    correct_align, error_align, r, score = align.perform_alignment(correct_seq, error_seq, match_weights=[1, -1], gap_penalties=[-3, -3, -3, -3])

    print(''.join(r))

    all_align_records.append(r)
    correct_seqs_all.extend(correct_seq)
    errors = []

    err_to_class = {'O': 0, '~': 1, '+': 2, '-': 3}

    most_recent_correct_note = np.zeros(inds_subset.shape)

    for i in range(len(correct_align)):

        error_note = error_align[i]
        correct_note = correct_align[i]
        if r[i] == '~':
            res = correct_note - error_note
            error_notes['replace_mod'].append(res)
        elif r[i] == '+' and type(error_note) != str:
            error_notes['insert_mod'].append(error_note)

        if not type(correct_note) == str:
            most_recent_correct_note = correct_note
        prev_entries = [err_to_class[r[i - x]] if i - x >= 0  else err_to_class[r[0]] for x in range(1, ngram + 1)]
        sample = np.concatenate([prev_entries, most_recent_correct_note])
        label = err_to_class[r[i]]
        X.append(sample)
        Y.append(label)

err_gen = elgr.ErrorGenerator(ngram, labeled_data=[X,Y], repl_samples=error_notes['replace_mod'], ins_samples=error_notes['insert_mod'])
err_gen.save_models('./quartet_omr_error_models.joblib')

