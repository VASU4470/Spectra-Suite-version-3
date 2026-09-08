import matplotlib.patches as patches
from matplotlib.patches import Ellipse
from matplotlib.lines import Line2D
from matplotlib.transforms import IdentityTransform
import numpy as np
from copy import deepcopy

class AnnotationManager:
    def __init__(
        self,
        canvas,
        on_select_callback=None,
        on_list_update_callback=None,
        text_input_provider=None,
    ):
        self.canvas = canvas
        self.on_select_callback = on_select_callback
        self.on_list_update_callback = on_list_update_callback # NEW: Tells GUI when list changes
        self.text_input_provider = text_input_provider
        self.active_tool = "none"
        
        self.annotations = []
        self.selected_artist = None
        
        self.start_x = None
        self.start_y = None
        self.active_ax = None
        self.drag_start_pos = None
        self.drag_original = None
        self.drag_handle = None
        self.selection_handles = []

        self.cid_press = self.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_drag = self.canvas.mpl_connect('motion_notify_event', self.on_drag)
        self.cid_release = self.canvas.mpl_connect('button_release_event', self.on_release)
        self.clipboard = None # Stores the copied object's properties
        self.undo_stack = []
        self.redo_stack = []
        self.history_limit = 100
        self.cid_key = self.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.cid_draw = self.canvas.mpl_connect('draw_event', self._on_draw)

    def _on_draw(self, _event):
        """Keep text underlines aligned after zooming, resizing, or panning."""
        changed = False
        for artist, kind in self.annotations:
            if kind == 'text' and getattr(artist, '_spectra_underline', False):
                changed = self._update_text_underline(artist) or changed
        if changed:
            self.canvas.draw_idle()

    def _update_text_underline(self, artist):
        line = getattr(artist, '_spectra_underline_line', None)
        if line is None:
            return False
        try:
            renderer = self.canvas.get_renderer()
            bounds = artist.get_window_extent(renderer=renderer)
        except (AttributeError, RuntimeError, ValueError):
            return False
        x_values = np.asarray([bounds.x0, bounds.x1], dtype=float)
        y_values = np.asarray([bounds.y0 - 1.5, bounds.y0 - 1.5], dtype=float)
        old_x = np.asarray(line.get_xdata(), dtype=float)
        old_y = np.asarray(line.get_ydata(), dtype=float)
        changed = (
            old_x.shape != x_values.shape or old_y.shape != y_values.shape
            or not np.allclose(old_x, x_values) or not np.allclose(old_y, y_values)
        )
        line.set_data(x_values, y_values)
        line.set_color(artist.get_color())
        line.set_alpha(artist.get_alpha())
        line.set_linewidth(max(0.8, float(artist.get_fontsize()) / 12.0))
        return changed

    def _set_text_underline(self, artist, enabled):
        line = getattr(artist, '_spectra_underline_line', None)
        if not enabled:
            if line is not None:
                line.remove()
            artist._spectra_underline = False
            artist._spectra_underline_line = None
            return
        if line is None:
            line = Line2D(
                [], [], transform=IdentityTransform(), color=artist.get_color(),
                linewidth=max(0.8, float(artist.get_fontsize()) / 12.0),
                zorder=artist.get_zorder() + 0.1, clip_on=True,
            )
            artist.axes.add_line(line)
            artist._spectra_underline_line = line
        artist._spectra_underline = True
        self._update_text_underline(artist)

    def select_by_index(self, idx):
        """Allows the GUI listbox to select an object without clicking the graph."""
        if 0 <= idx < len(self.annotations):
            artist, kind = self.annotations[idx]
            self._select_artist(artist, kind)
            self.canvas.draw_idle()

    def set_tool(self, tool_name):
        self.active_tool = tool_name
        self.clear_selection()

    def clear_selection(self):
        self.selected_artist = None
        self._remove_handles()
        if self.on_select_callback:
            self.on_select_callback(None, None)
        self.canvas.draw_idle()

    def on_press(self, event):
        if event.button != 1 or not event.inaxes: return
        self.start_x, self.start_y = event.xdata, event.ydata
        self.active_ax = event.inaxes

        # Existing annotations always take priority over the drawing tool. This
        # makes a direct click switch naturally into object-edit mode.
        handle = self._nearest_handle(event)
        if handle is not None and self.selected_artist:
            self._checkpoint()
            self.active_tool = "none"
            self.drag_handle = handle
            self.drag_original = self._geometry(*self.selected_artist)
            return
        for artist, kind in reversed(self.annotations):
            contains, _ = artist.contains(event)
            if contains:
                self._checkpoint()
                self.active_tool = "none"
                self._select_artist(artist, kind)
                self.drag_original = self._geometry(artist, kind)
                self.drag_handle = "move"
                return

        if self.active_tool == "none":
            self.clear_selection()
            return

        # --- DRAWING MODE (Added picker=15 for easy clicking) ---
        artist = None
        kind = self.active_tool
        self._checkpoint()
        
        if kind == "rect":
            artist = patches.Rectangle((self.start_x, self.start_y), 0, 0, linewidth=2, edgecolor='blue', facecolor='none', zorder=10, picker=15)
            self.active_ax.add_patch(artist)
        elif kind == "circle":
            # Using Ellipse so it scales smoothly on non-square axes
            artist = Ellipse((self.start_x, self.start_y), width=0, height=0, linewidth=2, edgecolor='green', facecolor='none', zorder=10, picker=15)
            self.active_ax.add_patch(artist)
        elif kind == "line":
            artist = Line2D([self.start_x, self.start_x], [self.start_y, self.start_y], color='purple', linewidth=2, linestyle='--', zorder=10, picker=15)
            self.active_ax.add_line(artist)
        elif kind == "arrow":
            artist = patches.FancyArrowPatch((self.start_x, self.start_y), (self.start_x, self.start_y), arrowstyle='->', color='red', mutation_scale=20, linewidth=2, zorder=10, picker=15)
            self.active_ax.add_patch(artist)
        elif kind == "text":
            text_value = self.text_input_provider() if self.text_input_provider else None
            if isinstance(text_value, dict):
                text_str = text_value.get("text")
                text_color = text_value.get("color", "black")
                text_size = text_value.get("fontsize", 12)
                text_weight = "bold" if text_value.get("bold") else "normal"
                text_style = "italic" if text_value.get("italic") else "normal"
                text_family = text_value.get("family", "sans-serif")
                text_underline = bool(text_value.get("underline", False))
            else:
                text_str = text_value
                text_color, text_size = "black", 12
                text_weight, text_style, text_family = "normal", "normal", "sans-serif"
                text_underline = False
            if text_str:
                artist = self.active_ax.text(self.start_x, self.start_y, text_str, color=text_color, fontsize=text_size, fontweight=text_weight, fontstyle=text_style, fontfamily=text_family,
                             bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray', linewidth=1), zorder=10, picker=15)
                self._set_text_underline(artist, text_underline)
            self.start_x = None

        if artist:
            self.annotations.append((artist, kind))
            self.selected_artist = (artist, kind)
            self._refresh_handles()
            if self.on_select_callback: self.on_select_callback(artist, kind)
            # NEW: Update the GUI listbox
            if self.on_list_update_callback: self.on_list_update_callback(self.annotations)

    def on_drag(self, event):
        if self.start_x is None or not event.inaxes or self.active_ax != event.inaxes: return
        dx, dy = event.xdata - self.start_x, event.ydata - self.start_y

        if self.active_tool == "none" and self.selected_artist and self.drag_original:
            artist, kind = self.selected_artist
            self._apply_geometry_drag(artist, kind, event.xdata, event.ydata, dx, dy)
            self._refresh_handles()
            self.canvas.draw_idle()
            return

        if self.selected_artist and self.active_tool != "none":
            artist, kind = self.selected_artist
            if kind == "rect":
                artist.set_width(dx)
                artist.set_height(dy)
            elif kind == "circle":
                # Scale width and height by 2 so the starting click acts as the center
                artist.width = abs(dx) * 2
                artist.height = abs(dy) * 2
            elif kind == "line":
                artist.set_xdata([self.start_x, event.xdata])
                artist.set_ydata([self.start_y, event.ydata])
            elif kind == "arrow":
                artist.set_positions((self.start_x, self.start_y), (event.xdata, event.ydata))
            self._refresh_handles()
            self.canvas.draw_idle()

    def on_release(self, event):
        self.start_x = None
        self.start_y = None
        self.drag_start_pos = None
        self.drag_original = None
        self.drag_handle = None

    def _geometry(self, artist, kind):
        if kind == 'text':
            return {'position': tuple(artist.get_position())}
        if kind == 'rect':
            return {'x': artist.get_x(), 'y': artist.get_y(),
                    'width': artist.get_width(), 'height': artist.get_height()}
        if kind == 'circle':
            return {'center': tuple(artist.center), 'width': artist.width, 'height': artist.height}
        if kind == 'arrow':
            return {'a': tuple(artist._posA_posB[0]), 'b': tuple(artist._posA_posB[1])}
        if kind == 'line':
            return {'x': np.asarray(artist.get_xdata(), float).copy(),
                    'y': np.asarray(artist.get_ydata(), float).copy()}
        return {}

    def _select_artist(self, artist, kind):
        self.selected_artist = (artist, kind)
        self.active_ax = artist.axes
        self.drag_start_pos = None
        self._refresh_handles()
        if self.on_select_callback:
            self.on_select_callback(artist, kind)

    def _handle_positions(self, artist, kind):
        if kind == 'text':
            return {'move': tuple(artist.get_position())}
        if kind == 'line':
            x, y = artist.get_xdata(), artist.get_ydata()
            return {'start': (x[0], y[0]), 'end': (x[-1], y[-1])}
        if kind == 'arrow':
            a, b = artist._posA_posB
            return {'start': tuple(a), 'end': tuple(b)}
        if kind == 'rect':
            x, y, w, h = artist.get_x(), artist.get_y(), artist.get_width(), artist.get_height()
            return {'sw': (x, y), 'se': (x + w, y), 'nw': (x, y + h), 'ne': (x + w, y + h)}
        if kind == 'circle':
            cx, cy = artist.center; hw, hh = artist.width / 2, artist.height / 2
            return {'left': (cx - hw, cy), 'right': (cx + hw, cy),
                    'bottom': (cx, cy - hh), 'top': (cx, cy + hh)}
        return {}

    def _remove_handles(self):
        for handle in self.selection_handles:
            try:
                handle.remove()
            except (ValueError, AttributeError):
                pass
        self.selection_handles = []

    def _refresh_handles(self):
        self._remove_handles()
        if not self.selected_artist:
            return
        artist, kind = self.selected_artist
        for name, (x, y) in self._handle_positions(artist, kind).items():
            handle = Line2D([x], [y], marker='s', markersize=6, markerfacecolor='white',
                            markeredgecolor='#2563eb', markeredgewidth=1.4,
                            linestyle='None', zorder=20, clip_on=False)
            handle._spectra_handle_name = name
            artist.axes.add_line(handle)
            self.selection_handles.append(handle)

    def _nearest_handle(self, event):
        if not self.selected_artist or event.x is None or event.y is None:
            return None
        artist, kind = self.selected_artist
        closest = None
        for name, point in self._handle_positions(artist, kind).items():
            pixel = artist.axes.transData.transform(point)
            distance = float(np.hypot(pixel[0] - event.x, pixel[1] - event.y))
            if distance <= 10 and (closest is None or distance < closest[0]):
                closest = (distance, name)
        return closest[1] if closest else None

    def _apply_geometry_drag(self, artist, kind, x, y, dx, dy):
        original, handle = self.drag_original, self.drag_handle
        if handle == 'move':
            if kind == 'text':
                px, py = original['position']; artist.set_position((px + dx, py + dy)); self._update_text_underline(artist)
            elif kind == 'rect':
                artist.set_xy((original['x'] + dx, original['y'] + dy))
            elif kind == 'circle':
                cx, cy = original['center']; artist.center = (cx + dx, cy + dy)
            elif kind == 'arrow':
                a, b = original['a'], original['b']; artist.set_positions((a[0]+dx, a[1]+dy), (b[0]+dx, b[1]+dy))
            elif kind == 'line':
                artist.set_data(original['x'] + dx, original['y'] + dy)
            return
        if kind == 'line':
            xs, ys = original['x'].copy(), original['y'].copy()
            index = 0 if handle == 'start' else -1; xs[index], ys[index] = x, y
            artist.set_data(xs, ys)
        elif kind == 'arrow':
            a, b = original['a'], original['b']
            artist.set_positions((x, y) if handle == 'start' else a,
                                 (x, y) if handle == 'end' else b)
        elif kind == 'rect':
            x0, y0 = original['x'], original['y']; x1 = x0 + original['width']; y1 = y0 + original['height']
            if 'w' in handle: x0 = x
            if 'e' in handle: x1 = x
            if 's' in handle: y0 = y
            if 'n' in handle: y1 = y
            artist.set_xy((x0, y0)); artist.set_width(x1 - x0); artist.set_height(y1 - y0)
        elif kind == 'circle':
            cx, cy = original['center']; left = cx-original['width']/2; right = cx+original['width']/2
            bottom = cy-original['height']/2; top = cy+original['height']/2
            if handle == 'left': left = x
            elif handle == 'right': right = x
            elif handle == 'bottom': bottom = y
            elif handle == 'top': top = y
            artist.center = ((left+right)/2, (bottom+top)/2)
            artist.width, artist.height = abs(right-left), abs(top-bottom)
        
    def delete_selected(self):
        if self.selected_artist:
            self._checkpoint()
            artist, kind = self.selected_artist
            if kind == 'text':
                self._set_text_underline(artist, False)
            artist.remove()
            self.annotations.remove(self.selected_artist)
            self.clear_selection()
            # NEW: Update the GUI listbox
            if self.on_list_update_callback: self.on_list_update_callback(self.annotations)

    def update_selected_properties(self, props):
        if not self.selected_artist: return
        self._checkpoint()
        artist, kind = self.selected_artist
        
        if kind == 'text':
            if 'text' in props: artist.set_text(props['text'])
            if 'color' in props: artist.set_color(props['color'])
            if 'fontsize' in props: artist.set_fontsize(props['fontsize'])
            if 'family' in props: artist.set_fontfamily(props['family'])
            if 'bold' in props: artist.set_fontweight('bold' if props['bold'] else 'normal')
            if 'italic' in props: artist.set_fontstyle('italic' if props['italic'] else 'normal')
            if 'text_alpha' in props: artist.set_alpha(props['text_alpha'])
            if 'underline' in props: self._set_text_underline(artist, props['underline'])
            self._update_text_underline(artist)

            bbox = artist.get_bbox_patch()
            if bbox:
                if 'box_alpha' in props: bbox.set_alpha(props['box_alpha'])
                if 'show_border' in props:
                    bbox.set_edgecolor('gray' if props['show_border'] else 'none')
                    bbox.set_linewidth(1 if props['show_border'] else 0)
        else:
            if 'color' in props:
                if kind == 'line': artist.set_color(props['color'])
                else: artist.set_edgecolor(props['color'])
            if 'linewidth' in props: artist.set_linewidth(props['linewidth'])
            if 'alpha' in props: artist.set_alpha(props['alpha'])
            
        self.canvas.draw_idle()
    def on_key_press(self, event):
        """Listens for keyboard commands on the graph canvas."""
        # Check for both Windows (ctrl) and Mac (cmd) keybindings
        if event.key in ['ctrl+z', 'cmd+z']:
            self.undo()
        elif event.key in ['ctrl+shift+z', 'cmd+shift+z', 'ctrl+y', 'cmd+y']:
            self.redo()
        elif event.key in ['ctrl+c', 'cmd+c'] and self.selected_artist:
            self.copy_selected()
        elif event.key in ['ctrl+v', 'cmd+v'] and self.clipboard:
            self.paste_clipboard()
        elif event.key in ['delete', 'backspace'] and self.selected_artist:
            self.delete_selected()
        elif event.key in ['up', 'down', 'left', 'right'] and self.selected_artist:
            self.nudge_selected(event.key)

    def copy_selected(self):
        """Extracts properties of the selected object into a clipboard dictionary."""
        if not self.selected_artist: return
        artist, kind = self.selected_artist
        
        clip = {'kind': kind}
        if kind == 'rect':
            clip['xy'] = artist.get_xy(); clip['w'] = artist.get_width(); clip['h'] = artist.get_height()
            clip['ec'] = artist.get_edgecolor(); clip['lw'] = artist.get_linewidth(); clip['alpha'] = artist.get_alpha()
        elif kind == 'circle':
            clip['center'] = artist.center; clip['w'] = artist.width; clip['h'] = artist.height
            clip['ec'] = artist.get_edgecolor(); clip['lw'] = artist.get_linewidth(); clip['alpha'] = artist.get_alpha()
        elif kind == 'text':
            clip['pos'] = artist.get_position(); clip['text'] = artist.get_text(); clip['c'] = artist.get_color()
            clip['fs'] = artist.get_fontsize(); clip['fw'] = artist.get_fontweight(); clip['fsy'] = artist.get_fontstyle()
            clip['family'] = artist.get_fontfamily()[0] if artist.get_fontfamily() else 'sans-serif'
            clip['underline'] = bool(getattr(artist, '_spectra_underline', False))
            clip['alpha'] = artist.get_alpha()
            bbox = artist.get_bbox_patch()
            clip['box_alpha'] = bbox.get_alpha() if bbox else 1.0
            clip['box_ec'] = bbox.get_edgecolor() if bbox else 'none'
        elif kind == 'arrow':
            clip['posA'] = artist._posA_posB[0]; clip['posB'] = artist._posA_posB[1]
            clip['c'] = artist.get_edgecolor(); clip['lw'] = artist.get_linewidth()
        elif kind == 'line':
            clip['x'] = artist.get_xdata(); clip['y'] = artist.get_ydata()
            clip['c'] = artist.get_color(); clip['lw'] = artist.get_linewidth(); clip['ls'] = artist.get_linestyle()
        
        self.clipboard = clip

    def paste_clipboard(self):
        """Creates a new object from the clipboard, offset slightly so it doesn't overlap perfectly."""
        if not self.clipboard or not self.active_ax: return
        self._checkpoint()
        clip = self.clipboard
        kind = clip['kind']
        
        # Calculate a tiny visual offset based on the axis range
        xlim, ylim = self.active_ax.get_xlim(), self.active_ax.get_ylim()
        dx, dy = (xlim[1] - xlim[0]) * 0.02, (ylim[1] - ylim[0]) * 0.02
        
        artist = None
        if kind == 'rect':
            artist = patches.Rectangle((clip['xy'][0]+dx, clip['xy'][1]+dy), clip['w'], clip['h'], linewidth=clip['lw'], edgecolor=clip['ec'], facecolor='none', zorder=10, picker=15, alpha=clip['alpha'])
            self.active_ax.add_patch(artist)
        elif kind == 'circle':
            artist = Ellipse((clip['center'][0]+dx, clip['center'][1]+dy), width=clip['w'], height=clip['h'], linewidth=clip['lw'], edgecolor=clip['ec'], facecolor='none', zorder=10, picker=15, alpha=clip['alpha'])
            self.active_ax.add_patch(artist)
        elif kind == 'text':
            artist = self.active_ax.text(clip['pos'][0]+dx, clip['pos'][1]+dy, clip['text'], color=clip['c'], fontsize=clip['fs'], fontweight=clip['fw'], fontstyle=clip['fsy'], fontfamily=clip.get('family', 'sans-serif'), alpha=clip['alpha'],
                                         bbox=dict(facecolor='white', alpha=clip['box_alpha'], edgecolor=clip['box_ec'], linewidth=1 if clip['box_ec']!='none' else 0), zorder=10, picker=15)
            self._set_text_underline(artist, clip.get('underline', False))
        elif kind == 'arrow':
            artist = patches.FancyArrowPatch((clip['posA'][0]+dx, clip['posA'][1]+dy), (clip['posB'][0]+dx, clip['posB'][1]+dy), arrowstyle='->', color=clip['c'], mutation_scale=20, linewidth=clip['lw'], zorder=10, picker=15)
            self.active_ax.add_patch(artist)
        elif kind == 'line':
            artist = Line2D([x+dx for x in clip['x']], [y+dy for y in clip['y']], color=clip['c'], linewidth=clip['lw'], linestyle=clip['ls'], zorder=10, picker=15)
            self.active_ax.add_line(artist)

        if artist:
            self.annotations.append((artist, kind))
            self.selected_artist = (artist, kind)
            if self.on_select_callback: self.on_select_callback(artist, kind)
            if self.on_list_update_callback: self.on_list_update_callback(self.annotations)
            self.canvas.draw_idle()

    def nudge_selected(self, key):
        """Moves the selected object slightly based on arrow keys."""
        if not self.selected_artist: return
        self._checkpoint()
        artist, kind = self.selected_artist
        xlim, ylim = self.active_ax.get_xlim(), self.active_ax.get_ylim()
        
        # This math automatically accounts for FTIR's reversed X-axis!
        step_x = (xlim[1] - xlim[0]) * 0.005
        step_y = (ylim[1] - ylim[0]) * 0.005
        
        dx, dy = 0, 0
        if key == 'left': dx = -step_x
        elif key == 'right': dx = step_x
        elif key == 'up': dy = step_y
        elif key == 'down': dy = -step_y

        if kind == 'text':
            pos = artist.get_position()
            artist.set_position((pos[0] + dx, pos[1] + dy))
            self._update_text_underline(artist)
        elif kind == 'rect':
            artist.set_x(artist.get_x() + dx)
            artist.set_y(artist.get_y() + dy)
        elif kind == 'circle':
            artist.center = (artist.center[0] + dx, artist.center[1] + dy)
        elif kind == 'arrow':
            pA, pB = artist._posA_posB
            artist.set_positions((pA[0] + dx, pA[1] + dy), (pB[0] + dx, pB[1] + dy))
        elif kind == 'line':
            artist.set_xdata(np.asarray(artist.get_xdata()) + dx)
            artist.set_ydata(np.asarray(artist.get_ydata()) + dy)
        self._refresh_handles()
        self.canvas.draw_idle()

    def _checkpoint(self):
        """Store the current annotation state before a user-visible change."""
        snapshot = deepcopy(self.get_serialized_data())
        if not self.undo_stack or self.undo_stack[-1] != snapshot:
            self.undo_stack.append(snapshot)
            del self.undo_stack[:-self.history_limit]
        self.redo_stack.clear()

    def _clear_artists(self):
        self._remove_handles()
        for artist, kind in list(self.annotations):
            if kind == 'text':
                self._set_text_underline(artist, False)
            try:
                artist.remove()
            except (ValueError, AttributeError):
                pass
        self.annotations = []
        self.selected_artist = None

    def _restore(self, snapshot):
        if self.active_ax is None:
            return
        self._clear_artists()
        self.load_serialized_data(deepcopy(snapshot), self.active_ax)
        self.clear_selection()
        if self.on_list_update_callback:
            self.on_list_update_callback(self.annotations)
        self.canvas.draw_idle()

    def undo(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(deepcopy(self.get_serialized_data()))
        self._restore(self.undo_stack.pop())
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(deepcopy(self.get_serialized_data()))
        self._restore(self.redo_stack.pop())
        return True

    def clear_all(self):
        if not self.annotations:
            return False
        self._checkpoint()
        self._clear_artists()
        if self.on_list_update_callback:
            self.on_list_update_callback(self.annotations)
        self.canvas.draw_idle()
        return True
    
    def get_serialized_data(self):
        """Converts all drawn objects into a dictionary format for JSON saving."""
        data = []
        for artist, kind in self.annotations:
            clip = {'kind': kind}
            if kind == 'rect':
                clip['xy'] = artist.get_xy(); clip['w'] = artist.get_width(); clip['h'] = artist.get_height()
                clip['ec'] = artist.get_edgecolor(); clip['lw'] = artist.get_linewidth(); clip['alpha'] = artist.get_alpha()
            elif kind == 'circle':
                clip['center'] = artist.center; clip['w'] = artist.width; clip['h'] = artist.height
                clip['ec'] = artist.get_edgecolor(); clip['lw'] = artist.get_linewidth(); clip['alpha'] = artist.get_alpha()
            elif kind == 'text':
                clip['pos'] = artist.get_position(); clip['text'] = artist.get_text(); clip['c'] = artist.get_color()
                clip['fs'] = artist.get_fontsize(); clip['fw'] = artist.get_fontweight(); clip['fsy'] = artist.get_fontstyle()
                clip['family'] = artist.get_fontfamily()[0] if artist.get_fontfamily() else 'sans-serif'
                clip['underline'] = bool(getattr(artist, '_spectra_underline', False))
                clip['alpha'] = artist.get_alpha()
                bbox = artist.get_bbox_patch()
                clip['box_alpha'] = bbox.get_alpha() if bbox else 1.0
                clip['box_ec'] = bbox.get_edgecolor() if bbox else 'none'
            elif kind == 'arrow':
                clip['posA'] = artist._posA_posB[0]; clip['posB'] = artist._posA_posB[1]
                clip['c'] = artist.get_edgecolor(); clip['lw'] = artist.get_linewidth()
            elif kind == 'line':
                clip['x'] = list(artist.get_xdata()); clip['y'] = list(artist.get_ydata())
                clip['c'] = artist.get_color(); clip['lw'] = artist.get_linewidth(); clip['ls'] = artist.get_linestyle()
            data.append(clip)
        return data

    def load_serialized_data(self, data_list, ax):
        """Rebuilds shapes from JSON data onto the graph."""
        import matplotlib.patches as patches
        from matplotlib.patches import Ellipse
        from matplotlib.lines import Line2D
        
        self.active_ax = ax
        for clip in data_list:
            kind = clip['kind']
            artist = None
            if kind == 'rect':
                artist = patches.Rectangle(clip['xy'], clip['w'], clip['h'], linewidth=clip['lw'], edgecolor=clip['ec'], facecolor='none', zorder=10, picker=15, alpha=clip.get('alpha', 1.0))
                ax.add_patch(artist)
            elif kind == 'circle':
                artist = Ellipse(clip['center'], width=clip['w'], height=clip['h'], linewidth=clip['lw'], edgecolor=clip['ec'], facecolor='none', zorder=10, picker=15, alpha=clip.get('alpha', 1.0))
                ax.add_patch(artist)
            elif kind == 'text':
                artist = ax.text(clip['pos'][0], clip['pos'][1], clip['text'], color=clip['c'], fontsize=clip['fs'], fontweight=clip['fw'], fontstyle=clip['fsy'], fontfamily=clip.get('family', 'sans-serif'), alpha=clip.get('alpha', 1.0),
                                 bbox=dict(facecolor='white', alpha=clip.get('box_alpha', 1.0), edgecolor=clip.get('box_ec', 'none'), linewidth=1 if clip.get('box_ec', 'none')!='none' else 0), zorder=10, picker=15)
                self._set_text_underline(artist, clip.get('underline', False))
            elif kind == 'arrow':
                artist = patches.FancyArrowPatch(clip['posA'], clip['posB'], arrowstyle='->', color=clip['c'], mutation_scale=20, linewidth=clip['lw'], zorder=10, picker=15)
                ax.add_patch(artist)
            elif kind == 'line':
                artist = Line2D(clip['x'], clip['y'], color=clip['c'], linewidth=clip['lw'], linestyle=clip.get('ls', '-'), zorder=10, picker=15)
                ax.add_line(artist)

            if artist:
                self.annotations.append((artist, kind))
        
        if self.on_list_update_callback:
            self.on_list_update_callback(self.annotations)
