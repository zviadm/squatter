import json

_FILENAME = "squat1.mov"

def _cm(track_window):
    """Center of mass for tracking window."""
    return (track_window[0] + track_window[2]/2, track_window[1] + track_window[3]/2)

def _sq_distance(cm1, cm2):
    return (cm1[0]-cm2[0])**2 + (cm1[1]-cm2[1])**2


if __name__ == '__main__':
    with open(_FILENAME+".squatter", "r") as f:
        tracking_data = json.loads(f.read())
        track_first_frame = tracking_data["first_frame"]
        track_windows = tracking_data["track_windows"]

    w_idx = 0
    min_squat_distance = 2*track_windows[0][3]
    min_back_range = 1/2 * track_windows[0][3]

    while w_idx < len(track_windows):
        w_start_cm = _cm(track_windows[w_idx])
        w_start_idx = w_idx
        w_max_cm = _cm(track_windows[w_idx])
        w_max_idx = w_idx
        w_idx += 1
        while True:
            if w_idx >= len(track_windows):
                # No REP. Time to exit.
                break
            cur_cm = _cm(track_windows[w_idx])
            if cur_cm[1] > w_max_cm[1]:
                w_max_cm = cur_cm
                w_max_idx = w_idx

            if ((w_max_cm[1] > w_start_cm[1] + min_squat_distance) and
                (cur_cm[1] < w_start_cm[1] + min_back_range)):
                # We have found bottom of the Squat, which is at w_max_cm.
                # Now time to find finishing frame.
                end_dst = _sq_distance(cur_cm, w_start_cm)
                end_idx = w_idx
                w_idx += 1
                while w_idx < len(track_windows):
                    cur_cm = _cm(track_windows[w_idx])
                    if cur_cm[1] > w_start_cm[1] + 2*min_back_range:
                        break
                    cur_dst = _sq_distance(cur_cm, w_start_cm)
                    if cur_dst < end_dst:
                        end_dst = cur_dst
                        end_idx = w_idx
                    w_idx += 1
                # Found a full REP, w_start_idx, w_max_idx, end_idx
                print ("REP",
                        w_start_idx, _cm(track_windows[w_start_idx]), " -- ",
                        w_max_idx, _cm(track_windows[w_max_idx]), " -- ",
                        end_idx, _cm(track_windows[end_idx]))
                w_idx = end_idx
                break
            w_idx += 1
