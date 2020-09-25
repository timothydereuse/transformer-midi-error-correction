import numpy as np
from collections import namedtuple, Counter
import os


def arr_to_runlength(arr, deltas, pitch_range, monophonic=False):
    '''
    takes in a processed array generated by make_hdf5.py and turns it into a run-length encoding.
    for now, it collapses all non-drum channels down into a single piano roll.
    '''

    tick_deltas_mapping = {v: i for i, v in enumerate(deltas)}
    MIDIEvent = namedtuple("MIDIEvent", "type voice note tick")

    def dict_add(dict, event):
        if event.tick in dict.keys():
            dict[event.tick].append(event)
        else:
            dict[event.tick] = [event]

    events = {}

    for n in arr:
        clp_pitch = int(np.clip(n[0], pitch_range[0], pitch_range[1]))
        start_event = MIDIEvent(
            type='start', voice=0, note=clp_pitch, tick=n[1])
        end_event = MIDIEvent(
            type='end', voice=0, note=clp_pitch, tick=n[2] + n[1])

        dict_add(events, start_event)
        dict_add(events, end_event)

    # structure of a change point:
    # [1] absolute tick time of event in natural numbers
    # [128] onset marker in {0, 1}
    # [128] active note in {0, 1}

    # alternative way is to use new arrays for each monophonic voice.

    note_ons_rl = []
    note_holds_rl = []
    note_deltas_rl = []

    num_notes = pitch_range[1] - pitch_range[0]
    pitch_start = pitch_range[0]

    sorted_events = sorted(list(events.keys()))

    for i, t in enumerate(sorted_events):

        note_ons = np.zeros(num_notes, dtype='int16') - 1
        note_holds = np.zeros(num_notes, dtype='int16') - 1
        deltas = np.zeros(len(tick_deltas_mapping))

        # get length after this change point
        try:
            delta = sorted_events[i + 1] - t
            delta_ind = tick_deltas_mapping[delta]
        except IndexError:
            # if this is at the end of the file, assign the longest possible value
            delta_ind = -1
        except KeyError:
            # if this delta is uncommon, find the nearest common one
            delta_keys = np.array(list(tick_deltas_mapping.keys()))
            best_ind = np.argmin(np.abs(delta_keys - delta))
            delta_ind = tick_deltas_mapping[delta_keys[best_ind]]

        deltas[delta_ind] = 1

        # for notes whose statuses are set directly by notes involved in the current change point,
        # what do do is obvious:
        for change in events[t]:
            ind = change.note - pitch_start - 1
            if change.type == 'start':
                note_ons[ind] = 1
                note_holds[ind] = 1
            elif change.type == 'end':
                note_ons[ind] = 0
                note_holds[ind] = 0

        # for onset-controlling indices, they're always off if not set explicitly on
        note_ons[note_ons == -1] = 0

        # for hold-controlling indices, we copy their previous state
        try:
            prev_note_hold = note_holds_rl[-1]
        except IndexError:
            prev_note_hold = np.zeros(num_notes, dtype='int16')

        note_holds[note_holds == -1] = prev_note_hold[note_holds == -1]

        # run_length.append(pt)
        note_ons_rl.append(note_ons)
        note_holds_rl.append(note_holds)
        note_deltas_rl.append(deltas)

    if monophonic:
        new_note_holds = np.sum(np.stack(note_holds_rl), 1)
        new_note_holds = 1 - np.clip(new_note_holds, 0, 1)
        note_holds_rl = np.expand_dims(new_note_holds, 1)

    run_length = np.concatenate([
        np.stack(note_holds_rl),
        np.stack(note_ons_rl),
        np.stack(note_deltas_rl)], 1)

    if monophonic:
        assert run_length.shape[-1] == pitch_range[1] - pitch_range[0] \
                                       + len(tick_deltas_mapping) + 1

    return run_length


def arr_to_runlength_mono(arr, deltas, pitch_range, flags):
    pitches = arr[:, 0]
    # onsets = arr[:, 1]
    durs = arr[:, 2]
    num_notes = len(pitches)
    # ends = onsets + durs

    # set rests to be one pitch higher than the pitch range.
    pitches[pitches != 0] = np.clip(pitches[pitches != 0], pitch_range[0], pitch_range[1])
    pitches[pitches == 0] = pitch_range[0] - 1
    pitches -= (pitch_range[0] - 1)

    pitch_mat = np.zeros([num_notes, 2 + pitch_range[1] - pitch_range[0]])
    # make list of indices by stacking pitches with integer range
    pitch_inds = list(np.stack([np.arange(0, num_notes), pitches], 0))
    pitch_mat[tuple(pitch_inds)] = 1

    # get indices for duration by taking difference of delta mapping keys and durs
    asdf = np.reshape(np.repeat(deltas, num_notes), [-1, num_notes])
    asdf = np.abs(asdf - durs)
    dur_locs = np.argmin(asdf, 0)

    # apply it to the duration matrix in the same way as we did with pitches
    dur_inds = list(np.stack([np.arange(0, num_notes), dur_locs], 0))
    dur_mat = np.zeros([num_notes, len(deltas)])
    dur_mat[tuple(dur_inds)] = 1

    # make empty flags
    empty_flags = np.zeros((num_notes, len(flags)))
    res = np.concatenate([pitch_mat, dur_mat, empty_flags], 1)

    return res


def arr_to_note_tuple(arr):
    sorted_notes = sorted(arr, key=lambda x: x[1])
    res = np.zeros_like(arr)
    last_onset_time = 0
    for i, n in enumerate(sorted_notes):

        # MIDI pitch
        res[i, 0] = n[0]

        # delta
        res[i, 1] = n[1] - last_onset_time
        last_onset_time = n[1]

        # duration
        res[i, 2] = n[2]
    return res


if __name__ == '__main__':
    import data_loaders as dl
    import h5py
    from time import time

    dset_path = 'essen_meertens_songs.hdf5'
    f = h5py.File(dset_path, 'r')
    num_songs = 500
    num_dur_vals = 10

    fnames = dl.all_hdf5_keys(f)
    np.random.shuffle(fnames)
    fnames = fnames[:num_songs]

    deltas, pitch_range = dl.get_tick_deltas_for_runlength(f, fnames, num_dur_vals, 0.2)

    start_time = time()
    for i in range(num_songs):
        arr = f[fnames[i]]
        x = arr_to_runlength_mono(arr, deltas, pitch_range)
    elapsed = time() - start_time

    print(f'{elapsed:4.4f} s, avg {elapsed * 1000/ num_songs:4.4f} ms per song')
