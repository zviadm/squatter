import json
import os


import cv2
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.graphics.texture import Texture
from kivy.graphics import Color, Rectangle, Line, InstructionGroup
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.properties import ObjectProperty
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.relativelayout import RelativeLayout

from track_squat import extract_reps, _sq_distance, _cm

_SQUATTER_EXT=".squatter"

class LoadDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)
    cwd = ObjectProperty(None)

class ExerciseDialog(FloatLayout):
    process = ObjectProperty(None)

class FrameCapture(object):

    def __init__(self, filename, frame_canvas, track_first_frame=None, track_windows=None):
        self._rotate = 0
        # TODO(zviad): figure out how to make this work with PyInstaller.
        import pymediainfo
        media_info = pymediainfo.MediaInfo.parse(filename)
        for track in media_info.tracks:
            if track.track_type.lower() != "video": continue
            rot_degree = int(float(track.to_data().get("rotation", 0)))
            while rot_degree >= 90:
                rot_degree -= 90
                self._rotate += 1
            break
        self._cap = cv2.VideoCapture(filename)
        self._frame_canvas = frame_canvas
        self._track_first_frame = track_first_frame
        self._track_windows = track_windows

    def release(self):
        self._cap.release()

    def n_frames(self):
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def fps(self):
        return self._cap.get(cv2.CAP_PROP_FPS)

    def _read_frame(self):
        ret, frame = self._cap.read()
        if not ret:
            return None
        for _ in range(self._rotate):
            frame = cv2.flip(frame, 0)
            frame = cv2.transpose(frame, 0)
        return frame


    def frame_for_canvas(self, frame_n):
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_n)
        self._cap.set(cv2.CAP_PROP_CONVERT_RGB, True)
        frame = self._read_frame()
        if frame is None: return None, None

        canvas_w, canvas_h = int(self._frame_canvas.width), int(self._frame_canvas.height)
        frame_w, frame_h = len(frame[0]), len(frame)
        self._frame_orig_size = (frame_w, frame_h)
        # Decide which way to resize the image, to keep aspect ratio intact.
        if frame_w * canvas_h > frame_h * canvas_w:
            frame_h = int(frame_h * canvas_w / frame_w)
            frame_w = canvas_w
            pos_x = 0
            pos_y = (canvas_h - frame_h)/2
        else:
            frame_w = int(frame_w * canvas_h / frame_h)
            frame_h = canvas_h
            pos_x = (canvas_w - frame_w)/2
            pos_y = 0
        frame = cv2.resize(frame, (frame_w, frame_h))
        self._frame_size = (frame_w, frame_h)
        self._frame_pos = (pos_x, pos_y)
        return (pos_x, pos_y), frame

    def track_window_for_canvas(self, frame_n):
        if (self._track_first_frame is None or
                frame_n < self._track_first_frame or
                frame_n >= self._track_first_frame+len(self._track_windows)):
            return None
        track_window = self._track_windows[frame_n-self._track_first_frame]
        canvas_track_window = (
            int(track_window[0] * self._frame_size[0] / self._frame_orig_size[0]),
            int(track_window[1] * self._frame_size[1] / self._frame_orig_size[1]),
            int(track_window[2] * self._frame_size[0] / self._frame_orig_size[0]),
            int(track_window[3] * self._frame_size[1] / self._frame_orig_size[1]))

        canvas_track_window = (
            self._frame_pos[0] + canvas_track_window[0],
            self._frame_pos[1] + self._frame_size[1] -
                canvas_track_window[1] - canvas_track_window[3], # Need to flip Y axis...
            canvas_track_window[2],
            canvas_track_window[3])
        return canvas_track_window

    def canvas_xy_to_frame_xy(self, x, y):
        frame_x = x - self._frame_pos[0]
        if frame_x < 0 or frame_x >= self._frame_size[0]:
            return None
        frame_y = self._frame_pos[1] + self._frame_size[1] - y
        if frame_y < 0 or frame_y >= self._frame_size[1]:
            return None

        frame_x = int(frame_x * self._frame_orig_size[0] / self._frame_size[0])
        frame_y = int(frame_y * self._frame_orig_size[1] / self._frame_size[1])
        return (frame_x, frame_y)

    def track_start(self, x, y, w, h, frame_n):
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_n)
        self._cap.set(cv2.CAP_PROP_CONVERT_RGB, True)

        frame = self._read_frame()
        assert frame is not None, "Frame number out of Bounds!"

        self._track_first_frame = frame_n
        self._track_windows = [(x,y,w,h)]
        self._tracker = cv2.Tracker_create("MEDIANFLOW")
        ok = self._tracker.init(frame, self._track_windows[-1])
        assert ok, "Failed to initialize tracker!"

    def track_next(self):
        """Should be called until returns False"""
        print ("FRAME N", self._cap.get(cv2.CAP_PROP_POS_FRAMES), self._track_windows[-1])
        frame = self._read_frame()
        if frame is None: return None
        ok, track_window = self._tracker.update(frame)
        if not ok:
            print("Tracker no longer available!", track_window)
            return None
        self._track_windows.append(track_window)
        print ("Track window", track_window)
        return frame




class FrameCanvas(RelativeLayout):

    def __init__(self, app):
        super(FrameCanvas, self).__init__()
        self._app = app
        self.bind(width=app.seek_video)
        self.bind(height=app.seek_video)
        self.touch_points = []

        self._select_event = None
        self._select_center_xy = None
        self._select_radius = None
        self._select_circle = None

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos): return False
        if self._app._cap is None: return False
        if self._app._play_pause_btn.text != "Play": return False

        canvas_xy = (touch.pos[0]-self.pos[0], touch.pos[1]-self.pos[1])
        if ((self._select_center_xy is None) or
                (_sq_distance(canvas_xy, self._select_center_xy) >= self._select_radius ** 2)):
            self._select_center_xy = canvas_xy
            self._select_radius = 0
            if self._select_circle is not None:
                self.canvas.remove(self._select_circle)
                self._select_circle = None

        if self._select_event is not None:
            self._select_event.cancel()
        self._select_event = Clock.schedule_interval(self._inc_selection, 0.01)
        return True

    def _inc_selection(self, *args, **kwargs):
        self._select_radius += 1
        frame_xy1 = self._app._cap.canvas_xy_to_frame_xy(
                self._select_center_xy[0] - self._select_radius,
                self._select_center_xy[1] + self._select_radius)
        frame_xy2 = self._app._cap.canvas_xy_to_frame_xy(
                self._select_center_xy[0] + self._select_radius,
                self._select_center_xy[1] - self._select_radius)
        if frame_xy1 is None or frame_xy2 is None:
            self._select_radius -= 1
            return
        if self._select_circle is not None:
            self.canvas.remove(self._select_circle)
        self._select_circle = InstructionGroup()
        self._select_circle.add(Color(1, 0, 0))
        self._select_circle.add(
                Line(circle=(self._select_center_xy) + (self._select_radius, ), width=dp(3)))
        self.canvas.add(self._select_circle)

    def on_touch_up(self, touch):
        if self._select_event is not None:
            self._select_event.cancel()
            self._select_event = None
        if self._select_center_xy is not None:
            self._app._process_btn.disabled = False

    def clear_selection(self):
        self.on_touch_up(None)
        if self._select_circle is not None:
            self.canvas.remove(self._select_circle)
            self._select_circle = None
        self._select_center_xy = None
        self._select_radius = None
        self._app._process_btn.disabled = True

    def get_selection(self):
        if self._select_center_xy is None:
            return None
        frame_xy1 = self._app._cap.canvas_xy_to_frame_xy(
                self._select_center_xy[0] - self._select_radius,
                self._select_center_xy[1] + self._select_radius)
        frame_xy2 = self._app._cap.canvas_xy_to_frame_xy(
                self._select_center_xy[0] + self._select_radius,
                self._select_center_xy[1] - self._select_radius)
        return (frame_xy1, frame_xy2)

class RepCanvas(RelativeLayout):

    def __init__(self, app,  exercise, track_windows, bottom_idx, start_frame,**kwargs):
        super(RepCanvas, self).__init__(**kwargs)
        assert exercise in ["squat", "deadlift"]
        self._app = app
        self._start_frame = start_frame
        self._exercise = exercise

        self._cms = [_cm(w) for w in track_windows]
        self._min_x = min(cm[0] for cm in self._cms)
        self._min_y = min(cm[1] for cm in self._cms)
        self._max_x = max(cm[0] for cm in self._cms)
        self._max_y = max(cm[1] for cm in self._cms)
        self._bottom_idx = bottom_idx
        self._start_frame = start_frame
        self.bind(width=self._redraw)
        self.bind(height=self._redraw)

    def _redraw(self, *args, **kwargs):
        scale = (self.height * 0.9) / (self._max_y - self._min_y)
        x_adj = (self.width - ((self._max_x - self._min_x) * scale)) / 2
        y_adj = (self.height - ((self._max_y - self._min_y) * scale)) / 2

        def _convert_xy(xy):
            return (
                    (xy[0] - self._min_x) * scale + x_adj,
                    self.height - ((xy[1] - self._min_y) * scale + y_adj))

        _line_width = dp(3)
        with self.canvas:
            Color(1, 1, 1)
            Line(points=(
                _convert_xy(self._cms[0]) +
                _convert_xy(self._cms[self._bottom_idx])), width=_line_width)
            if self._exercise == "squat":
                Color(1, 0, 0)
                Line(points=[p
                    for cm in self._cms[:self._bottom_idx]
                    for p in _convert_xy(cm)], width=_line_width)
                Color(0, 1, 0)
                Line(points=[p
                    for cm in self._cms[self._bottom_idx:]
                    for p in _convert_xy(cm) ], width=_line_width)
            elif self._exercise == "deadlift":
                Color(0, 1, 0)
                Line(points=[p
                    for cm in self._cms[:self._bottom_idx]
                    for p in _convert_xy(cm)], width=_line_width)
                # Don't care about bar path going down during deadlifts.

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos): return False
        self._app.change_frame_to(self._start_frame)
        return True


class SquatterApp(App):

    def build(self):
        play_pause_btn = Button(text='Play', size_hint_x=None, width=dp(60))
        play_pause_btn.bind(on_release=self._on_play_pause)
        self._play_pause_btn = play_pause_btn

        frame_canvas = FrameCanvas(self)
        frame_slider = Slider(min=0, max=0, value=0)
        frame_slider.bind(value=self.seek_video)
        load_btn = Button(text='Load')
        load_btn.bind(on_release=self._load_video)
        process_btn = Button(text='Process', disabled=True)
        process_btn.bind(on_release=self._process_video)

        btn_layout = GridLayout(cols=2, size_hint_y=None, height=dp(40))
        btn_layout.add_widget(load_btn)
        btn_layout.add_widget(process_btn)
        slider_layout = GridLayout(cols=2, size_hint_y=None, height=dp(40))
        slider_layout.add_widget(play_pause_btn)
        slider_layout.add_widget(frame_slider)
        video_layout = GridLayout(cols=1)
        video_layout.add_widget(frame_canvas)
        video_layout.add_widget(slider_layout)
        video_layout.add_widget(btn_layout)

        rep_layout_inner = GridLayout(cols=3, size_hint_y=None)
        rep_layout_inner.bind(minimum_height=rep_layout_inner.setter('height'))
        rep_layout = ScrollView(size_hint_x=None, width=dp(200))
        rep_layout.add_widget(rep_layout_inner)

        main_layout = GridLayout(cols=2)
        main_layout.add_widget(video_layout)
        main_layout.add_widget(rep_layout)

        self._frame_canvas = frame_canvas
        self._frame_slider = frame_slider
        self._btn_layout = btn_layout
        self._process_btn = process_btn
        self._cap = None
        self._rep_layout = rep_layout_inner
        self._squatter_file = None

        _keyboard = None
        def _keyboard_closed():
            _keyboard.unbind(on_key_down=self._on_keyboard_down)
        _keyboard = Window.request_keyboard(_keyboard_closed, main_layout, 'text')
        if _keyboard.widget:
            # If it exists, this widget is a VKeyboard object which you can use
            # to change the keyboard layout.
            pass
        _keyboard.bind(on_key_down=self._on_keyboard_down)
        return main_layout

    def _on_play_pause(self, instance):
        if self._play_pause_btn.text == "Play":
            if self._cap is None: return
            self.change_play_pause("Pause")
            def _play(*args, **kwargs):
                if self._play_pause_btn.text == "Pause":
                    if self._frame_slider.value+1 >= self._frame_slider.max:
                        self.change_play_pause("Play")
                    else:
                        self._frame_slider.value += 1
                        Clock.schedule_once(_play, 0.5/self._cap.fps())
            Clock.schedule_once(_play, 0.5/self._cap.fps())
        elif self._play_pause_btn.text == "Pause":
            self.change_play_pause("Play")
        elif self._play_pause_btn.text == "Stop":
            self.change_play_pause("Play")

    def change_play_pause(self, new_text):
        self._play_pause_btn.text = new_text


    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        slider_delta = 15
        if ("alt" in modifiers) or ("meta" in modifiers):
            slider_delta = 1
        if keycode[1] == 'left':
            self._frame_slider.value = max(
                self._frame_slider.value - slider_delta, self._frame_slider.min)
        elif keycode[1] == 'right':
            self._frame_slider.value = min(
                self._frame_slider.value + slider_delta, self._frame_slider.max)
        else:
            return False
        # TODO(zviad): Figure out how to update UI when Key is held.
        return True

    def _dismiss_popup(self):
        self._popup.dismiss()

    def _load_video(self, instance):
        if self._squatter_file is None:
            cwd = os.getcwd()
        else:
            cwd = os.path.dirname(self._squatter_file)
        content = LoadDialog(
            load=self._load_video_file, cancel=self._dismiss_popup, cwd=cwd)
        self._popup = Popup(title="Select Video", content=content, size_hint=(0.9, 0.9))
        self._popup.open()

    def _load_video_file(self, path, filename):
        if self._cap:
            self._cap.release()
        exercise = None
        track_first_frame = None
        track_windows = None
        filepath = os.path.join(path, filename[0])
        self._squatter_file = filepath+_SQUATTER_EXT
        if os.path.exists(self._squatter_file):
            with open(self._squatter_file, "r") as f:
                tracking_data = json.loads(f.read())
                exercise = tracking_data["exercise"]
                track_first_frame = tracking_data["first_frame"]
                track_windows = tracking_data["track_windows"]
        self._cap = FrameCapture(
            filepath, self._frame_canvas,
            track_first_frame=track_first_frame, track_windows=track_windows)
        self._cap._exercise = exercise
        self._process_tracking_info()

        self.change_frame_to(track_first_frame or 0)
        self._frame_slider.max = self._cap.n_frames()-1
        self.seek_video(None, None)
        self._dismiss_popup()

    def _process_tracking_info(self):
        self._rep_layout.clear_widgets()
        track_first_frame, track_windows = self._cap._track_first_frame, self._cap._track_windows
        if track_first_frame is None: return

        reps = extract_reps(self._cap._exercise, track_windows)
        print ("TrackingInfo:", track_first_frame,
                "Reps (", self._cap._exercise, "):", len(reps))

        for rep_idx, rep in enumerate(reps):
            l = GridLayout(cols=1, size_hint_y=None, height=dp(230))
            l.add_widget(
                    Label(text="Rep {}".format(rep_idx+1), size_hint_y=None, height=dp(30)))
            l.add_widget(
                    RepCanvas(
                        self, self._cap._exercise, track_windows[rep[0]:rep[2]],
                        rep[1]-rep[0], rep[0] + track_first_frame,
                        size_hint_y=None, height=dp(200)))
            self._rep_layout.add_widget(l)

    def _process_video(self, instance):
        content = ExerciseDialog(process=self._process_exercise)
        self._popup = Popup(
                title="Select Exercise", content=content,
                size_hint=(None, None), size=(dp(200), dp(200)))
        self._popup.open()

    def _process_exercise(self, exercise):
        self._dismiss_popup()
        points = self._frame_canvas.get_selection()
        assert points is not None

        self._frame_slider.disabled = True
        self._btn_layout.disabled = True
        self.change_play_pause("Stop")
        self._cap.track_start(
                points[0][0], points[0][1],
                points[1][0]-points[0][0], points[1][1]-points[0][1],
                int(self._frame_slider.value))
        interval_secs = 0.1/self._cap.fps() # Try as fast as possible.
        def _track_it(dt):
            f = self._cap.track_next()
            if f is None or self._play_pause_btn.text != "Stop":
                self._frame_slider.disabled = False
                self._btn_layout.disabled = False
                self._process_btn.disabled = True
                self._process_tracking_info()
                self.change_play_pause("Play")

                d = {
                    "exercise": exercise,
                    "first_frame": self._cap._track_first_frame,
                    "track_windows": self._cap._track_windows}
                with open(self._squatter_file, "w") as f:
                    f.write(json.dumps(d, indent=4))
                return
            self._frame_slider.value += 1
            Clock.schedule_once(_track_it, interval_secs)
        Clock.schedule_once(_track_it, interval_secs)

    def change_frame_to(self, frame_n):
        self._frame_slider.value = frame_n

    def seek_video(self, _i, _v):
        if not self._cap: return
        self._frame_canvas.clear_selection()
        frame_pos, frame = self._cap.frame_for_canvas(int(self._frame_slider.value))
        if frame is None:
            print ("WARNING: Failed to fetch a frame properly!", int(self._frame_slider.value))
            return
        # Frame needs to flipped because Kivy coordinates are bottom up.
        frame = cv2.flip(frame, 0)
        frame_size = (len(frame[0]), len(frame))
        t = Texture.create(size=frame_size, colorfmt="bgr")
        t.blit_buffer(frame.tostring(), bufferfmt="ubyte", colorfmt="bgr")


        self._frame_canvas.canvas.clear()
        self._frame_canvas.canvas.add(
                Rectangle(pos=frame_pos, texture=t, size=frame_size))

        track_window = self._cap.track_window_for_canvas(int(self._frame_slider.value))
        if track_window is not None:
            self._frame_canvas.canvas.add(Color(1, 0, 0))
            self._frame_canvas.canvas.add(
                    Line(rectangle=track_window[:2] + track_window[2:], width=dp(3)))
        self._frame_canvas.canvas.ask_update()

Factory.register('LoadDialog', cls=LoadDialog)
Factory.register('ExerciseDialog', cls=ExerciseDialog)

if __name__ == '__main__':
    SquatterApp().run()

