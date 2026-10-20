"""Small, dependency-free desktop controls with keyboard and focus support."""
import tkinter as tk
from tkinter import font as tkfont

BG = '#F6F7FB'
PAPER = '#FFFFFF'
TEXT = '#232737'
MUTED = '#626B7D'
LINE = '#E7E9F1'
ACCENT = '#6555D9'
SOFT = '#EFEDFC'
INPUT = '#FCFCFE'
NAV = '#FCFCFF'
HOVER = '#F2F0FA'
CONTROL_LINE = '#B0ACBE'
ON_ACCENT = '#FFFFFF'


def rounded(canvas, x1, y1, x2, y2, radius, **kwargs):
    r = min(radius, max(0, (x2-x1)/2), max(0, (y2-y1)/2))
    fill, edge, width = kwargs.get('fill', ''), kwargs.get('outline', ''), kwargs.get('width', 1)
    canvas.create_rectangle(x1+r,y1,x2-r,y2,fill=fill,outline='')
    canvas.create_rectangle(x1,y1+r,x2,y2-r,fill=fill,outline='')
    for box,start in [((x1,y1,x1+2*r,y1+2*r),90),((x2-2*r,y1,x2,y1+2*r),0),
                      ((x2-2*r,y2-2*r,x2,y2),270),((x1,y2-2*r,x1+2*r,y2),180)]:
        canvas.create_arc(*box,start=start,extent=90,fill=fill,outline='')
        if edge:canvas.create_arc(*box,start=start,extent=90,style='arc',outline=edge,width=width)
    if edge:
        for coords in [(x1+r,y1,x2-r,y1),(x1+r,y2,x2-r,y2),(x1,y1+r,x1,y2-r),(x2,y1+r,x2,y2-r)]:
            canvas.create_line(*coords,fill=edge,width=width)


class Surface(tk.Frame):
    def __init__(self, parent, color=PAPER, border=LINE, radius=16, padding=20, **kwargs):
        super().__init__(parent, bg=parent.cget('bg'), **kwargs)
        self.color, self.border, self.radius = color, border, radius
        self.canvas = tk.Canvas(self, bg=self.cget('bg'), bd=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=color)
        self.inner.pack(fill='both', expand=True, padx=padding, pady=padding)
        self.bind('<Configure>', self.draw)

    def draw(self, event=None):
        state = (self.winfo_width(), self.winfo_height(), self.color, self.border, self.radius)
        if getattr(self, '_drawn_state', None) == state:
            return
        self._drawn_state = state
        self.canvas.delete('all')
        rounded(self.canvas, 1, 1, self.winfo_width()-1, self.winfo_height()-1,
                self.radius, fill=self.color, outline=self.border, width=1)

    def focus_border(self, active):
        self.border = ACCENT if active else CONTROL_LINE
        self.draw()


class Button(tk.Canvas):
    def __init__(self, parent, text, command=None, kind='secondary', width=None,
                 height=40, font=None, state='normal', **kwargs):
        self.text, self.command, self.kind = text, command, kind
        self._state, self.hover, self.focused, self.selected = state, False, False, False
        self.font = font or tkfont.nametofont('TkDefaultFont')
        measure = tkfont.Font(font=self.font)
        width = width or measure.measure(text) + 32
        super().__init__(parent, width=width, height=height, bd=0, highlightthickness=0,
                         bg=parent.cget('bg'), takefocus=1, cursor='hand2', **kwargs)
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<FocusIn>', lambda e: self._focus(True))
        self.bind('<FocusOut>', lambda e: self._focus(False))
        self.bind('<ButtonRelease-1>', lambda e: self.invoke())
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())

    def _hover(self, value):
        self.hover = value
        self.draw()

    def _focus(self, value):
        self.focused = value
        self.draw()

    def set_selected(self, value):
        if self.selected == value:
            return
        self.selected = value
        self.draw()

    def invoke(self):
        if self._state != 'disabled' and self.command:
            self.focus_set()
            return self.command()

    def instate(self, states):
        return all((self._state == 'disabled') if s == 'disabled' else (self._state != 'disabled') for s in states)

    def configure(self, cnf=None, **kwargs):
        for key in ('text', 'state'):
            if key in kwargs:
                setattr(self, '_state' if key == 'state' else 'text', kwargs.pop(key))
        result = super().configure(cnf, **kwargs) if cnf or kwargs else None
        self.draw()
        return result

    config = configure

    def draw(self):
        state = (self.winfo_width(), self.winfo_height(), self._state, self.hover,
                 self.focused, self.selected, self.text, self.kind, str(self.font), self.cget('bg'))
        if getattr(self, '_drawn_state', None) == state:
            return
        self._drawn_state = state
        self.delete('all')
        color, foreground, edge = PAPER, TEXT, CONTROL_LINE
        if self.kind == 'primary':
            color, foreground, edge = ('#5847C7' if self.hover else ACCENT), ON_ACCENT, ACCENT
        elif self.kind == 'nav':
            color = SOFT if self.selected else (HOVER if self.hover else self.cget('bg'))
            foreground = ACCENT if self.selected else MUTED
            edge = color
        elif self.kind == 'segment':
            color = SOFT if self.selected else (HOVER if self.hover else self.cget('bg'))
            foreground = ACCENT if self.selected else MUTED
            edge = CONTROL_LINE if self.selected else color
        elif self.kind == 'ghost':
            color = HOVER if self.hover else self.cget('bg')
            edge, foreground = color, MUTED
        elif self.hover:
            color = HOVER
        if self._state == 'disabled':
            color, foreground, edge = '#F0EDF5', '#9B94A7', LINE
        if self.kind == 'selected':
            color, foreground, edge = SOFT, ACCENT, ACCENT
        if self.focused:
            edge = TEXT if self.kind == 'primary' else ACCENT
        rounded(self, 1, 1, self.winfo_width()-1, self.winfo_height()-1, 11,
                fill=color, outline=edge, width=2 if self.focused else 1)
        if self.kind == 'nav':
            self.create_text(16, self.winfo_height()/2, text=self.text, fill=foreground, font=self.font, anchor='w')
        else:
            self.create_text(self.winfo_width()/2, self.winfo_height()/2, text=self.text, fill=foreground, font=self.font)


class ProviderTile(tk.Canvas):
    def __init__(self, parent, title, subtitle, symbol, command, font, **kwargs):
        self.title_height=tkfont.Font(family=font,size=9,weight='bold').metrics('linespace')
        self.subtitle_height=tkfont.Font(family=font,size=8).metrics('linespace')
        self.tile_height=max(69,self.title_height+self.subtitle_height+30)
        super().__init__(parent, bg=parent.cget('bg'), height=self.tile_height, bd=0,
                         highlightthickness=0, takefocus=1, cursor='hand2', **kwargs)
        self.title, self.subtitle, self.symbol = title, subtitle, symbol
        self.command, self.font = command, font
        self.selected, self.focused = False, False
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<ButtonRelease-1>', lambda e: self.invoke())
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.bind('<FocusIn>', lambda e: self._focus(True))
        self.bind('<FocusOut>', lambda e: self._focus(False))

    def _focus(self, state):
        self.focused = state
        self.draw()

    def invoke(self):
        self.focus_set()
        self.command()

    def set_selected(self, state):
        if self.selected == state:
            return
        self.selected = state
        self.draw()

    def draw(self):
        state = (self.winfo_width(), self.winfo_height(), self.selected, self.focused)
        if getattr(self, '_drawn_state', None) == state:
            return
        self._drawn_state = state
        self.delete('all')
        w = self.winfo_width()
        fill, edge = (SOFT, ACCENT) if self.selected else (INPUT, CONTROL_LINE)
        if self.focused:
            edge = ACCENT
        rounded(self, 1, 1, w-1, self.tile_height-1, 10, fill=fill, outline=edge, width=2 if self.focused else 1)
        center=self.tile_height/2
        rounded(self, 13, center-16, 45, center+16, 7, fill='#E3DDF9' if self.selected else HOVER, outline='')
        self.create_text(29, center, text=self.symbol, font=(self.font, 13, 'bold'), fill=ACCENT if self.selected else '#817391')
        self.create_text(57, 13+self.title_height/2, text=self.title, anchor='w', font=(self.font, 9, 'bold'), fill=TEXT)
        self.create_text(57, 17+self.title_height+self.subtitle_height/2, text=self.subtitle, anchor='w', font=(self.font, 8), fill=MUTED)
        self.create_oval(w-25, 14, w-13, 26, fill=ACCENT if self.selected else INPUT, outline=ACCENT if self.selected else CONTROL_LINE)
        if self.selected:
            self.create_line(w-22,20,w-20,22,w-16,18, fill=ON_ACCENT, width=1.5)


class SlimScroll(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent, width=9, bg=parent.cget('bg'), bd=0, highlightthickness=0)
        self.command, self.first, self.last = command, 0, 1
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Button-1>', self.drag)
        self.bind('<B1-Motion>', self.drag)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.draw()

    def draw(self):
        state = (self.winfo_width(), self.winfo_height(), self.first, self.last)
        if getattr(self, '_drawn_state', None) == state:
            return
        self._drawn_state = state
        self.delete('all')
        if self.last-self.first < 0.999:
            h = self.winfo_height()
            rounded(self, 2, self.first*h, 7, max(self.first*h+16, self.last*h), 3,
                    fill=CONTROL_LINE, outline='')

    def drag(self, event):
        self.command('moveto', max(0, min(1, event.y/max(1,self.winfo_height()) - (self.last-self.first)/2)))
