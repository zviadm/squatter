import cv2
from pymediainfo import MediaInfo
from kivy.app import App
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.graphics import Rectangle
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.slider import Slider


class SquatterWidget(Widget):
    pass


class SquatterApp(App):

    def build(self):
        layout = GridLayout(cols=1)

        frame_canvas = Widget()
        frame_canvas.bind(width=self._seek_video)
        frame_canvas.bind(height=self._seek_video)
        frame_slider = Slider(min=0, max=0, value=0, size_hint_y=None, height=100)
        frame_slider.bind(value=self._seek_video)
        load_btn = Button(text='Load', size_hint_y=None, height=100)
        load_btn.bind(on_press=self._load_video)

        layout.add_widget(frame_canvas)
        layout.add_widget(frame_slider)
        layout.add_widget(load_btn)

        self._frame_canvas = frame_canvas
        self._frame_slider = frame_slider
        self._cap = None

        _keyboard = None
        def _keyboard_closed():
            _keyboard.unbind(on_key_down=self._on_keyboard_down)
        _keyboard = Window.request_keyboard(_keyboard_closed, layout, 'text')
        if _keyboard.widget:
            # If it exists, this widget is a VKeyboard object which you can use
            # to change the keyboard layout.
            pass
        _keyboard.bind(on_key_down=self._on_keyboard_down)
        return layout


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
        FILENAME = "testvid3.mov"
        media_info = MediaInfo.parse(FILENAME)
        self._cap_rotate = False
        for track in media_info.tracks:
            if track.track_type.lower() != "video": continue
            if int(float(track.to_data().get("rotation", 0))) == 90:
                self._cap_rotate = True
        self._cap = cv2.VideoCapture(FILENAME)
        self._frame_slider.max = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))-1
        self._frame_slider.value = 0
        self._seek_video(self._frame_slider, self._frame_slider.value)

    def _seek_video(self, _i, _v):
        if not self._cap: return
        canvas_w = int(self._frame_canvas.width)
        canvas_h = int(self._frame_canvas.height)

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._frame_slider.value)
        self._cap.set(cv2.CAP_PROP_CONVERT_RGB, True)
        ret, frame = self._cap.read()
        if self._cap_rotate:
            frame = cv2.flip(frame, 0)
            frame = cv2.transpose(frame, 0)
        # Frame needs to flipped because Kivy coordinates are bottom up.
        frame = cv2.flip(frame, 0)

        frame_w = len(frame[0])
        frame_h = len(frame)

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
        pos_x += self._frame_canvas.pos[0]
        pos_y += self._frame_canvas.pos[1]

        frame = cv2.resize(frame, (frame_w, frame_h))
        frame_w = len(frame[0])
        frame_h = len(frame)
        print(
            "Canvas size: {}:{} / Re---Sized {}:{}:{}".format(
                canvas_w, canvas_h, frame_w, frame_h, self._cap_rotate))

        t = Texture.create(size=(frame_w, frame_h), colorfmt="bgr")
        t.blit_buffer(frame.tostring(), bufferfmt="ubyte", colorfmt="bgr")
        self._frame_canvas.canvas.clear()
        self._frame_canvas.canvas.add(
                Rectangle(pos=(pos_x, pos_y), texture=t, size=(frame_w, frame_h)))
        self._frame_canvas.canvas.ask_update()


if __name__ == '__main__':
    SquatterApp().run()
