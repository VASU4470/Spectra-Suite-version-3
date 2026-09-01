import matplotlib.patches as patches
from matplotlib.patches import Ellipse
from matplotlib.lines import Line2D
import numpy as np

class AnnotationManager:
    def __init__(self, canvas, on_select_callback=None, on_list_update_callback=None):
        self.canvas = canvas
        self.on_select_callback = on_select_callback
        self.on_list_update_callback = on_list_update_callback # NEW: Tells GUI when list changes
        self.active_tool = "none"
        
        self.annotations = []
        self.selected_artist = None
        
        self.start_x = None
        self.start_y = None
        self.active_ax = None
        self.drag_start_pos = None

        self.cid_press = self.canvas.mpl_connect('button_press_event', self.on_press)
        self.cid_drag = self.canvas.mpl_connect('motion_notify_event', self.on_drag)
        self.cid_release = self.canvas.mpl_connect('button_release_event', self.on_release)
        self.clipboard = None # Stores the copied object's properties
        self.cid_key = self.canvas.mpl_connect('key_press_event', self.on_key_press)

    def select_by_index(self, idx):
        """Allows the GUI listbox to select an object without clicking the graph."""
        if 0 <= idx < len(self.annotations):
            self.selected_artist = self.annotations[idx]
            artist, kind = self.selected_artist
            
            # Setup dragging math in case they click the list, then drag the object
            if kind == 'text': self.drag_start_pos = artist.get_position()
            elif kind == 'rect': self.drag_start_pos = artist.get_xy()
            elif kind == 'circle': self.drag_start_pos = artist.center
            elif kind == 'arrow': self.drag_start_pos = (artist._posA_posB[0], artist._posA_posB[1])
            elif kind == 'line': self.drag_start_pos = (artist.get_xdata(), artist.get_ydata())
            
            if self.on_select_callback: self.on_select_callback(artist, kind)
            self.canvas.draw_idle()

    def set_tool(self, tool_name):
        self.active_tool = tool_name
        self.clear_selection()

    def clear_selection(self):
        self.selected_artist = None
        if self.on_select_callback:
            self.on_select_callback(None, None)
        self.canvas.draw_idle()

    def on_press(self, event):
        if event.button != 1 or not event.inaxes: return
        self.start_x, self.start_y = event.xdata, event.ydata
        self.active_ax = event.inaxes

        # --- SELECTION MODE (With increased sensitivity via 'picker') ---
        if self.active_tool == "none":
            for artist, kind in reversed(self.annotations):
                contains, _ = artist.contains(event)
                if contains:
                    self.selected_artist = (artist, kind)
                    if kind == 'text': self.drag_start_pos = artist.get_position()
                    elif kind == 'rect': self.drag_start_pos = artist.get_xy()
                    elif kind == 'circle': self.drag_start_pos = artist.center # Ellipse uses center
                    elif kind == 'arrow': self.drag_start_pos = (artist._posA_posB[0], artist._posA_posB[1])
                    elif kind == 'line': self.drag_start_pos = (artist.get_xdata(), artist.get_ydata())
                    
                    if self.on_select_callback: self.on_select_callback(artist, kind)
                    return
            self.clear_selection()
            return

        # --- DRAWING MODE (Added picker=15 for easy clicking) ---
        artist = None
        kind = self.active_tool
        
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
            from tkinter import simpledialog
            # Force the dialog to appear on top of the current canvas window
            parent_window = self.canvas.get_tk_widget().winfo_toplevel()
            text_str = simpledialog.askstring("Text Box", "Enter your annotation:", parent=parent_window)
            if text_str:
                artist = self.active_ax.text(self.start_x, self.start_y, text_str, color='black', fontsize=12, fontweight='normal', fontstyle='normal',
                             bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray', linewidth=1), zorder=10, picker=15)
            self.start_x = None

        if artist:
            self.annotations.append((artist, kind))
            self.selected_artist = (artist, kind)
            if self.on_select_callback: self.on_select_callback(artist, kind)
            # NEW: Update the GUI listbox
            if self.on_list_update_callback: self.on_list_update_callback(self.annotations)

    def on_drag(self, event):
        if self.start_x is None or not event.inaxes or self.active_ax != event.inaxes: return
        dx, dy = event.xdata - self.start_x, event.ydata - self.start_y

        if self.active_tool == "none" and self.selected_artist and self.drag_start_pos:
            artist, kind = self.selected_artist
            if kind == 'text': artist.set_position((self.drag_start_pos[0] + dx, self.drag_start_pos[1] + dy))
            elif kind == 'rect':
                artist.set_x(self.drag_start_pos[0] + dx)
                artist.set_y(self.drag_start_pos[1] + dy)
            elif kind == 'circle':
                artist.center = (self.drag_start_pos[0] + dx, self.drag_start_pos[1] + dy)
            elif kind == 'arrow':
                pA, pB = self.drag_start_pos
                artist.set_positions((pA[0] + dx, pA[1] + dy), (pB[0] + dx, pB[1] + dy))
            elif kind == 'line':
                xd, yd = self.drag_start_pos
                artist.set_xdata(xd + dx)
                artist.set_ydata(yd + dy)
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
            self.canvas.draw_idle()

    def on_release(self, event):
        self.start_x = None
        self.start_y = None
        self.drag_start_pos = None
        
    def delete_selected(self):
        if self.selected_artist:
            artist, kind = self.selected_artist
            artist.remove()
            self.annotations.remove(self.selected_artist)
            self.clear_selection()
            # NEW: Update the GUI listbox
            if self.on_list_update_callback: self.on_list_update_callback(self.annotations)

    def update_selected_properties(self, props):
        if not self.selected_artist: return
        artist, kind = self.selected_artist
        
        if kind == 'text':
            if 'text' in props: artist.set_text(props['text'])
            if 'color' in props: artist.set_color(props['color'])
            if 'fontsize' in props: artist.set_fontsize(props['fontsize'])
            if 'bold' in props: artist.set_fontweight('bold' if props['bold'] else 'normal')
            if 'italic' in props: artist.set_fontstyle('italic' if props['italic'] else 'normal')
            if 'text_alpha' in props: artist.set_alpha(props['text_alpha'])

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
        if event.key in ['ctrl+c', 'cmd+c'] and self.selected_artist:
            self.copy_selected()
        elif event.key in ['ctrl+v', 'cmd+v'] and self.clipboard:
            self.paste_clipboard()
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
            artist = self.active_ax.text(clip['pos'][0]+dx, clip['pos'][1]+dy, clip['text'], color=clip['c'], fontsize=clip['fs'], fontweight=clip['fw'], fontstyle=clip['fsy'], alpha=clip['alpha'],
                                         bbox=dict(facecolor='white', alpha=clip['box_alpha'], edgecolor=clip['box_ec'], linewidth=1 if clip['box_ec']!='none' else 0), zorder=10, picker=15)
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
        elif kind == 'rect':
            artist.set_x(artist.get_x() + dx)
            artist.set_y(artist.get_y() + dy)
        elif kind == 'circle':
            artist.center = (artist.center[0] + dx, artist.center[1] + dy)
        elif kind == 'arrow':
            pA, pB = artist._posA_posB
            artist.set_positions((pA[0] + dx, pA[1] + dy), (pB[0] + dx, pB[1] + dy))
        elif kind == 'line':
            artist.set_xdata(artist.get_xdata() + dx)
            artist.set_ydata(artist.get_ydata() + dy)
            
        self.canvas.draw_idle()
    
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
                artist = ax.text(clip['pos'][0], clip['pos'][1], clip['text'], color=clip['c'], fontsize=clip['fs'], fontweight=clip['fw'], fontstyle=clip['fsy'], alpha=clip.get('alpha', 1.0),
                                 bbox=dict(facecolor='white', alpha=clip.get('box_alpha', 1.0), edgecolor=clip.get('box_ec', 'none'), linewidth=1 if clip.get('box_ec', 'none')!='none' else 0), zorder=10, picker=15)
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