def _cm(track_window):
    """Center of mass for tracking window."""
    return (track_window[0] + track_window[2]/2, track_window[1] + track_window[3]/2)

def _sq_distance(cm1, cm2):
    return (cm1[0]-cm2[0])**2 + (cm1[1]-cm2[1])**2

def _extract_reps(track_windows,coeff=2.0):
    reps = []
    min_squat_distance = coeff*track_windows[0][3]
    min_back_range = 0.5*track_windows[0][3]
    cms = [_cm(w) for w in track_windows]

    idx = 0
    while idx < len(cms):
        min_cm = cms[idx]
        min_idx = idx
        max_cm = cms[idx]
        max_idx = idx
        while True:
            if idx >= len(cms):
                # No REP. But ran out of tracking frames.
                break
            cur_cm = cms[idx]
            if cur_cm[1] >= max_cm[1]:
                max_cm = cur_cm
                max_idx = idx

            if (max_cm[1] <= min_cm[1] + min_squat_distance) and (cur_cm[1] <= min_cm[1]):
                min_cm = cur_cm
                min_idx = idx

            if ((max_cm[1] > min_cm[1] + min_squat_distance) and
                (cur_cm[1] < min_cm[1] + min_back_range)):
                # We have found bottom of the Squat, which is at max_cm.
                # Now time to find finishing frame.
                end_dst = _sq_distance(cur_cm, min_cm)
                end_idx = idx
                idx += 1
                while idx < len(cms):
                    cur_cm = cms[idx]
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

def extract_squat_reps(track_windows,coeff=2.0):
    reps = _extract_reps(track_windows,coeff=coeff)
    squat_reps = []
    for min_idx, max_idx, end_idx in reps:
        _, ex = _trunc_rep(track_windows[max_idx:end_idx], end_p=0.90)
        squat_reps.append([min_idx, max_idx, max_idx+ex])
    return squat_reps


def extract_deadlift_reps(track_windows):
    track_windows_reverse = [(w[0], -w[1], w[2], w[3]) for w in track_windows]
    reps = _extract_reps(track_windows_reverse, coeff=1.25)
    dead_reps = []
    for min_idx, max_idx, end_idx in reps:
        sx, _ = _trunc_rep(track_windows_reverse[min_idx:max_idx], start_p=0.01, end_p=0.95)
        dead_reps.append([min_idx+sx, max_idx, end_idx])
    return dead_reps

def extract_reps(exercise, track_windows):
    _f = {
        "squat": extract_squat_reps,
        "deadlift": extract_deadlift_reps,
    }
    return _f[exercise](track_windows)

def _trunc_rep(track_windows, start_p=0.0, end_p=1.0):
    if not track_windows: return 0
    assert start_p < end_p

    cms = [_cm(w) for w in track_windows]
    start_dist = _sq_distance(cms[-1], cms[0]) * start_p
    end_dist = _sq_distance(cms[-1], cms[0]) * end_p
    start_idx = 0
    for idx, cm in enumerate(cms):
        if _sq_distance(cms[0], cm) <= start_dist:
            start_idx = idx
        if _sq_distance(cms[0], cm) >= end_dist:
            return start_idx, idx
    assert False, "Unreachable Code!"
