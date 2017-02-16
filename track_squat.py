def _cm(track_window):
    """Center of mass for tracking window."""
    return (track_window[0] + track_window[2]/2, track_window[1] + track_window[3]/2)

def _sq_distance(cm1, cm2):
    return (cm1[0]-cm2[0])**2 + (cm1[1]-cm2[1])**2

def extract_squat_reps(track_windows):
    reps = []
    min_squat_distance = 2.0*track_windows[0][3]
    min_back_range = 0.5*track_windows[0][3]

    idx = 0
    while idx < len(track_windows):
        while (idx+1 < len(track_windows) and
                _cm(track_windows[idx])[1] >= _cm(track_windows[idx+1])[1]):
            idx += 1

        min_cm = _cm(track_windows[idx])
        min_idx = idx
        max_cm = _cm(track_windows[idx])
        max_idx = idx
        while True:
            if idx >= len(track_windows):
                # No REP. But ran out of tracking frames.
                break
            cur_cm = _cm(track_windows[idx])
            if cur_cm[1] >= max_cm[1]:
                max_cm = cur_cm
                max_idx = idx

            if cur_cm[1] <= min_cm[1]:
                min_cm = cur_cm
                min_idx = idx

            if ((max_cm[1] > min_cm[1] + min_squat_distance) and
                (cur_cm[1] < min_cm[1] + min_back_range)):
                # We have found bottom of the Squat, which is at max_cm.
                # Now time to find finishing frame.

                end_dst = _sq_distance(cur_cm, min_cm)
                end_idx = idx
                idx += 1
                while idx < len(track_windows):
                    cur_cm = _cm(track_windows[idx])
                    if cur_cm[1] > min_cm[1] + 2*min_back_range:
                        break
                    cur_dst = _sq_distance(cur_cm, min_cm)
                    if cur_dst <= end_dst:
                        end_dst = cur_dst
                        end_idx = idx
                    idx += 1
                reps.append([min_idx, max_idx, end_idx])
                idx = end_idx
                break
            idx += 1
    return reps

def extract_deadlift_reps(track_windows):
    track_windows_reverse = [(w[0], -w[1], w[2], w[3]) for w in track_windows]
    reps = extract_squat_reps(track_windows_reverse)
    return reps

def extract_reps(exercise, track_windows):
    _f = {
        "squat": extract_squat_reps,
        "deadlift": extract_deadlift_reps,
    }
    return _f[exercise](track_windows)
