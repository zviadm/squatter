import cv2
import numpy
from pymediainfo import MediaInfo
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.graphics import Color, Rectangle
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.slider import Slider
from kivy.uix.relativelayout import RelativeLayout


class SquatterWidget(Widget):
    pass

class FrameCapture(object):

    def __init__(self, filename, frame_canvas):
        media_info = MediaInfo.parse(filename)
        self._rotate = 0
        for track in media_info.tracks:
            if track.track_type.lower() != "video": continue
            # TODO(zviad): handle 180/270 degree rotations too.
            rot_degree = int(float(track.to_data().get("rotation", 0)))
            while rot_degree >= 90:
                rot_degree -= 90
                self._rotate += 1
            break
        self._cap = cv2.VideoCapture(filename)
        self._track_first_frame = None
        self._frame_canvas = frame_canvas

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
        assert frame is not None, "Frame number out of Bounds!"
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
        if self._track_first_frame is None or frame_n < self._track_first_frame:
            return None
        track_window = self._track_windows[frame_n-self._track_first_frame]
        canvas_track_window = (
            self._frame_pos[0] + int(track_window[0] * self._frame_size[0] / self._frame_orig_size[0]),
            self._frame_pos[1] + int(track_window[1] * self._frame_size[1] / self._frame_orig_size[1]),
            int(track_window[2] * self._frame_size[0] / self._frame_orig_size[0]),
            int(track_window[3] * self._frame_size[1] / self._frame_orig_size[1]))

        canvas_track_window = (
            canvas_track_window[0],
            self._frame_size[1] - canvas_track_window[1] - canvas_track_window[3], # Need to flip Y axis...
            canvas_track_window[2],
            canvas_track_window[3])
        return canvas_track_window

    def frame_xy_to_canvas_xy(x, y):
        pass

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
        # set up the ROI for tracking
        roi = frame[y:y+h, x:x+w]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv_roi, numpy.array((0.,60.,32.)), numpy.array((180.,255.,255.)))
        roi_hist = cv2.calcHist([hsv_roi],[0],mask,[180],[0,180])
        cv2.normalize(roi_hist,roi_hist,0,255,cv2.NORM_MINMAX)

        self._track_first_frame = frame_n
        self._track_windows = [(x,y,w,h)]
        self._track_roi_hist = roi_hist
        self._track_term_crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 1)

    def track_next(self):
        """Should be called until returns False"""
        frame = self._read_frame()
        if frame is None: return None
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        dst = cv2.calcBackProject([hsv],[0],self._track_roi_hist,[0,180],1)
        ret, track_window = cv2.meanShift(dst, self._track_windows[-1], self._track_term_crit)
        self._track_windows.append(track_window)
        print ("Track window", track_window, "Ret", ret)
        return frame




class FrameCanvas(RelativeLayout):

    def __init__(self, app):
        super(FrameCanvas, self).__init__()
        self._app = app
        self.bind(width=app.seek_video)
        self.bind(height=app.seek_video)

    def on_touch_down(self, touch):
        if not self._app._cap: return False
        canvas_xy  = (touch.pos[0]-self.pos[0], touch.pos[1]-self.pos[1])
        frame_xy = self._app._cap.canvas_xy_to_frame_xy(*canvas_xy)
        frame_n = self._app._frame_slider.value
        print ("Point on Frame", frame_xy, frame_n)
        return False


class SquatterApp(App):

    def build(self):

        frame_canvas = FrameCanvas(self)
        frame_slider = Slider(min=0, max=0, value=0, size_hint_y=None, height=100)
        frame_slider.bind(value=self.seek_video)
        load_btn = Button(text='Load')
        load_btn.bind(on_press=self._load_video)
        process_btn = Button(text='Process')
        process_btn.bind(on_press=self._process_video)

        main_layout = GridLayout(cols=1)
        main_layout.add_widget(frame_canvas)
        main_layout.add_widget(frame_slider)
        btn_layout = GridLayout(cols=2, size_hint_y=None, height=100)
        btn_layout.add_widget(load_btn)
        btn_layout.add_widget(process_btn)
        main_layout.add_widget(btn_layout)

        self._frame_canvas = frame_canvas
        self._frame_slider = frame_slider
        self._cap = None

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


    def _load_video(self, instance):
        if self._cap:
            self._cap.release()
        self._cap = FrameCapture("testvid3.mov", self._frame_canvas)

        self._frame_slider.max = self._cap.n_frames()
        self._frame_slider.value = 0
        self.seek_video(self._frame_slider, self._frame_slider.value)

    def _process_video(self, instance):
        if not self._cap: return

        self._cap.track_start(259, 410, 409-259, 560-410, 0)
        self._frame_slider.value = 0
        self._frame_slider.disabled = True
        interval_secs = 0.5/self._cap.fps() # 2x original speed.
        def _track_it(dt):
            f = self._cap.track_next()
            if f is None:
                self._frame_slider.disabled = False
                return
            self._frame_slider.value += 1
            Clock.schedule_once(_track_it, interval_secs)
        Clock.schedule_once(_track_it, interval_secs)

    def seek_video(self, _i, _v):
        if not self._cap: return
        frame_pos, frame = self._cap.frame_for_canvas(int(self._frame_slider.value))
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
                    Rectangle(pos=track_window[:2], size=track_window[2:]))
        self._frame_canvas.canvas.ask_update()


if __name__ == '__main__':
    SquatterApp().run()
