from __future__ import annotations

import json
import multiprocessing as mp
import queue
import time
from pathlib import Path
from typing import Any

import wx
from PIL import Image as PILImage

from src.common import App
from src.models.map_session import MapSession
from src.services.map_service import load_map, save_map
from src.services.minimap_preview_service import (
    MINIMAP_EXTENDED,
    MINIMAP_EXTENDED_ZONE_OWNERS,
    MINIMAP_EXTENDED_ZONE_TYPES,
    MINIMAP_STANDARD,
    preview_layer_options,
    render_minimap_preview,
)

SECTIONS = [
    "general",
    "player_specs",
    "conditions",
    "teams",
    "starting_heroes",
    "ban_flags",
    "rumors",
    "hero_data",
    "terrain",
    "object_defs",
    "object_data",
    "town_events",
    "global_events",
]


class MainFrame(wx.Frame):
    CONFIG_FILE = Path.home() / ".h3mex" / "config.json"

    def __init__(self) -> None:
        super().__init__(None, title=App.NAME, size=(1200, 800))
        self.session = MapSession()
        self._current_dir = self._get_maps_directory()
        self._minimap_gap_size = 16
        self._minimap_resize_timer: wx.CallLater | None = None
        self._minimap_cached_image = None

        self._build_menu()
        self._build_layout()
        self._sync_layer_controls_state()
        self._update_title()
        self.CreateStatusBar()
        self.SetStatusText("Ready")

    def _build_menu(self) -> None:
        menubar = wx.MenuBar()

        file_menu = wx.Menu()
        self._item_open = file_menu.Append(wx.ID_OPEN, "&Open\tCtrl+O")
        self._item_reload = file_menu.Append(wx.ID_REFRESH, "&Reload\tCtrl+R")
        file_menu.AppendSeparator()
        self._item_save = file_menu.Append(wx.ID_SAVE, "&Save\tCtrl+S")
        self._item_save_as = file_menu.Append(wx.ID_SAVEAS, "Save &As\tCtrl+Shift+S")
        file_menu.AppendSeparator()
        self._item_exit = file_menu.Append(wx.ID_EXIT, "E&xit")

        settings_menu = wx.Menu()
        self._item_maps_dir = settings_menu.Append(wx.ID_ANY, "&Maps Directory...")

        menubar.Append(file_menu, "&File")
        menubar.Append(settings_menu, "&Settings")
        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, self.on_open, self._item_open)
        self.Bind(wx.EVT_MENU, self.on_reload, self._item_reload)
        self.Bind(wx.EVT_MENU, self.on_save, self._item_save)
        self.Bind(wx.EVT_MENU, self.on_save_as, self._item_save_as)
        self.Bind(wx.EVT_MENU, self.on_exit, self._item_exit)
        self.Bind(wx.EVT_MENU, self.on_change_maps_directory, self._item_maps_dir)

    def _build_layout(self) -> None:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel)
        self.section_controls: dict[str, wx.TextCtrl] = {}
        self._section_page_by_index: dict[int, str] = {}
        self._loaded_section_pages: set[str] = set()
        self._minimap_page_index: int | None = None
        self._minimap_panel: wx.Panel | None = None
        self._minimap_bitmap_container: wx.Panel | None = None
        self._minimap_bitmap: wx.StaticBitmap | None = None
        self._minimap_standard_toggle: wx.ToggleButton | None = None
        self._minimap_extended_toggle: wx.ToggleButton | None = None
        self._overlay_panel: wx.Panel | None = None
        self._layers_panel: wx.Panel | None = None
        self._overlay_default_radio: wx.RadioButton | None = None
        self._overlay_types_radio: wx.RadioButton | None = None
        self._overlay_owners_radio: wx.RadioButton | None = None
        self._layer_checks: dict[str, wx.CheckBox] = {}

        overview = wx.TextCtrl(self.notebook, style=wx.TE_MULTILINE | wx.TE_READONLY)
        overview.SetValue("No map loaded.")
        self.notebook.AddPage(overview, "Overview")
        self.section_controls["__overview__"] = overview
        self._section_page_by_index[0] = "__overview__"

        for section in SECTIONS:
            section_ctrl = wx.TextCtrl(self.notebook, style=wx.TE_MULTILINE | wx.TE_READONLY)
            section_ctrl.SetValue("No map loaded.")
            self.notebook.AddPage(section_ctrl, section)
            self.section_controls[section] = section_ctrl
            self._section_page_by_index[self.notebook.GetPageCount() - 1] = section

        minimap_panel = self._build_minimap_panel()
        self.notebook.AddPage(minimap_panel, "Minimap")
        self._minimap_page_index = self.notebook.GetPageCount() - 1
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_notebook_page_changed)

        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)

    def _build_minimap_panel(self) -> wx.Panel:
        panel = wx.Panel(self.notebook)
        self._minimap_panel = panel
        root_sizer = wx.BoxSizer(wx.VERTICAL)

        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(wx.StaticText(panel, label="Mode"), 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8)
        self._minimap_standard_toggle = wx.ToggleButton(panel, label="Standard")
        self._minimap_extended_toggle = wx.ToggleButton(panel, label="Extended")
        self._minimap_standard_toggle.SetValue(True)
        self._minimap_standard_toggle.Bind(wx.EVT_TOGGLEBUTTON, self.on_minimap_mode_toggled)
        self._minimap_extended_toggle.Bind(wx.EVT_TOGGLEBUTTON, self.on_minimap_mode_toggled)
        controls.Add(self._minimap_standard_toggle, 0, wx.RIGHT, 8)
        controls.Add(self._minimap_extended_toggle, 0)

        self._overlay_panel = wx.Panel(panel)
        overlay_sizer = wx.BoxSizer(wx.HORIZONTAL)
        overlay_sizer.Add(
            wx.StaticText(self._overlay_panel, label="Overlay"), 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 8
        )
        self._overlay_default_radio = wx.RadioButton(self._overlay_panel, label="Default", style=wx.RB_GROUP)
        self._overlay_default_radio.SetValue(True)
        self._overlay_types_radio = wx.RadioButton(self._overlay_panel, label="Zone Types")
        self._overlay_owners_radio = wx.RadioButton(self._overlay_panel, label="Zone Owners")
        self._overlay_default_radio.Bind(wx.EVT_RADIOBUTTON, self.on_minimap_overlay_changed)
        self._overlay_types_radio.Bind(wx.EVT_RADIOBUTTON, self.on_minimap_overlay_changed)
        self._overlay_owners_radio.Bind(wx.EVT_RADIOBUTTON, self.on_minimap_overlay_changed)
        overlay_sizer.Add(self._overlay_default_radio, 0, wx.RIGHT, 10)
        overlay_sizer.Add(self._overlay_types_radio, 0, wx.RIGHT, 10)
        overlay_sizer.Add(self._overlay_owners_radio, 0)
        self._overlay_panel.SetSizer(overlay_sizer)

        self._layers_panel = wx.Panel(panel)
        layers_box = wx.StaticBoxSizer(wx.VERTICAL, self._layers_panel, "Object Layers")
        layers_actions = wx.BoxSizer(wx.HORIZONTAL)
        select_all_btn = wx.Button(self._layers_panel, label="Select All")
        select_none_btn = wx.Button(self._layers_panel, label="Select None")
        select_all_btn.Bind(wx.EVT_BUTTON, self.on_layers_select_all)
        select_none_btn.Bind(wx.EVT_BUTTON, self.on_layers_select_none)
        layers_actions.Add(select_all_btn, 0, wx.RIGHT, 8)
        layers_actions.Add(select_none_btn, 0)

        layer_grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=4)
        for key, label in preview_layer_options():
            check = wx.CheckBox(self._layers_panel, label=label)
            check.SetValue(True)
            check.Bind(wx.EVT_CHECKBOX, self.on_minimap_layer_toggle)
            self._layer_checks[key] = check
            layer_grid.Add(check, 0)
        layers_box.Add(layers_actions, 0, wx.ALL, 6)
        layers_box.Add(layer_grid, 0, wx.ALL, 6)
        layers_root = wx.BoxSizer(wx.VERTICAL)
        layers_root.Add(layers_box, 0, wx.EXPAND)
        self._layers_panel.SetSizer(layers_root)

        self._minimap_bitmap_container = wx.Panel(panel)
        self._minimap_bitmap_container.Bind(wx.EVT_SIZE, self.on_minimap_container_resized)
        self._minimap_bitmap = wx.StaticBitmap(self._minimap_bitmap_container)
        self._minimap_bitmap.SetMinSize((320, 180))
        self._minimap_bitmap.SetSize((320, 180))
        self._place_minimap_bitmap((320, 180))

        root_sizer.Add(controls, 0, wx.ALL, 8)
        root_sizer.Add(self._overlay_panel, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root_sizer.Add(self._layers_panel, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root_sizer.Add(self._minimap_bitmap_container, 1, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(root_sizer)
        return panel

    def on_open(self, _event: wx.CommandEvent) -> None:
        with wx.FileDialog(
            self,
            "Open H3M map",
            defaultDir=str(self._current_dir),
            wildcard="H3M files (*.h3m)|*.h3m",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            selected_path = dialog.GetPath()

        self._load_file(selected_path)

    def on_reload(self, _event: wx.CommandEvent) -> None:
        if not self.session.is_loaded:
            wx.MessageBox("No map is currently loaded.", "Reload", wx.OK | wx.ICON_INFORMATION)
            return
        self._load_file(self.session.filename)

    def on_save(self, _event: wx.CommandEvent) -> None:
        if not self.session.is_loaded:
            wx.MessageBox("No map is currently loaded.", "Save", wx.OK | wx.ICON_INFORMATION)
            return

        try:
            saved_path = save_map(self.session.data, self.session.filename, source_filename=self.session.filename)
            self.session.filename = saved_path
            self.session.data["filename"] = saved_path
            self.session.mark_clean()
            self._update_title()
            self.SetStatusText(f"Saved {Path(saved_path).name}")
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(f"Save failed:\n{exc}", "Error", wx.OK | wx.ICON_ERROR)

    def on_save_as(self, _event: wx.CommandEvent) -> None:
        if not self.session.is_loaded:
            wx.MessageBox("No map is currently loaded.", "Save As", wx.OK | wx.ICON_INFORMATION)
            return

        with wx.FileDialog(
            self,
            "Save H3M map as",
            defaultDir=str(self._current_dir),
            defaultFile=Path(self.session.filename).name,
            wildcard="H3M files (*.h3m)|*.h3m",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            target_path = dialog.GetPath()

        try:
            saved_path = save_map(self.session.data, target_path, source_filename=self.session.filename)
            self.session.filename = saved_path
            self.session.data["filename"] = saved_path
            self.session.mark_clean()
            self._update_title()
            self.SetStatusText(f"Saved as {Path(saved_path).name}")
            self._render_sections()
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(f"Save As failed:\n{exc}", "Error", wx.OK | wx.ICON_ERROR)

    def on_exit(self, _event: wx.CommandEvent) -> None:
        self.Close(True)

    def on_minimap_mode_toggled(self, event: wx.CommandEvent) -> None:
        if self._minimap_standard_toggle is None or self._minimap_extended_toggle is None:
            return

        if event.GetEventObject() == self._minimap_standard_toggle:
            self._minimap_standard_toggle.SetValue(True)
            self._minimap_extended_toggle.SetValue(False)
        else:
            self._minimap_standard_toggle.SetValue(False)
            self._minimap_extended_toggle.SetValue(True)

        self._sync_layer_controls_state()
        self._render_minimap_preview()

    def on_minimap_overlay_changed(self, _event: wx.CommandEvent) -> None:
        self._render_minimap_preview()

    def on_minimap_layer_toggle(self, _event: wx.CommandEvent) -> None:
        self._render_minimap_preview()

    def on_layers_select_all(self, _event: wx.CommandEvent) -> None:
        for check in self._layer_checks.values():
            check.SetValue(True)
        self._render_minimap_preview()

    def on_layers_select_none(self, _event: wx.CommandEvent) -> None:
        for check in self._layer_checks.values():
            check.SetValue(False)
        self._render_minimap_preview()

    def on_notebook_page_changed(self, event: wx.BookCtrlEvent) -> None:
        selection = event.GetSelection()
        self._ensure_active_section_rendered(selection)
        if self._is_minimap_tab_active(selection):
            if self._minimap_cached_image is None:
                self._render_minimap_preview()
            else:
                self._refresh_minimap_display_only()
        event.Skip()

    def on_minimap_container_resized(self, event: wx.SizeEvent) -> None:
        if self._minimap_bitmap is not None:
            self._place_minimap_bitmap(self._minimap_bitmap.GetSize())

        if self.session.is_loaded and self._is_minimap_tab_active(self.notebook.GetSelection()):
            if self._minimap_resize_timer is not None and self._minimap_resize_timer.IsRunning():
                self._minimap_resize_timer.Stop()
            self._minimap_resize_timer = wx.CallLater(90, self._refresh_minimap_display_only)
        event.Skip()

    def _load_file(self, filepath: str) -> None:
        progress_dialog = wx.ProgressDialog(
            title="Loading map",
            message="Loading...",
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_ELAPSED_TIME,
        )

        ctx = mp.get_context("spawn")
        progress_queue = ctx.Queue()
        process = ctx.Process(target=_load_map_worker, args=(filepath, progress_queue), daemon=True)

        try:
            process.start()
            data: dict[str, Any] | None = None
            load_error: Exception | None = None

            while True:
                try:
                    kind, payload = progress_queue.get_nowait()
                    if kind == "progress":
                        progress_dialog.Pulse("Loading...")
                    elif kind == "result":
                        data = payload
                        break
                    elif kind == "error":
                        load_error = RuntimeError(payload)
                        break
                except queue.Empty:
                    progress_dialog.Pulse("Loading...")

                wx.YieldIfNeeded()
                if not process.is_alive() and progress_queue.empty():
                    break
                time.sleep(0.02)

            if load_error is not None:
                raise load_error
            if data is None:
                raise RuntimeError("Load process ended unexpectedly.")

            progress_dialog.Pulse("Loading...")
            wx.YieldIfNeeded()
            self.session.set_loaded_map(data["filename"], data)
            self._current_dir = str(Path(data["filename"]).parent)
            self._reset_section_views_for_new_map()
            self._render_overview_section()
            self._ensure_active_section_rendered(self.notebook.GetSelection())
            self._sync_layer_controls_state()
            progress_dialog.Pulse("Loading...")
            wx.YieldIfNeeded()
            self._minimap_cached_image = None
            if self._is_minimap_tab_active(self.notebook.GetSelection()):
                self._render_minimap_preview()
            self._update_title()
            self.SetStatusText(f"Loaded {Path(data['filename']).name}")
        except Exception as exc:  # noqa: BLE001
            wx.MessageBox(f"Open failed:\n{exc}", "Error", wx.OK | wx.ICON_ERROR)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            progress_dialog.Destroy()

    def _render_sections(self) -> None:
        # Kept for compatibility with earlier calls; now delegates to lazy behavior.
        self._reset_section_views_for_new_map()
        self._render_overview_section()
        self._ensure_active_section_rendered(self.notebook.GetSelection())

    def _reset_section_views_for_new_map(self) -> None:
        self._loaded_section_pages.clear()
        self.section_controls["__overview__"].SetValue("Loading overview...")
        for section in SECTIONS:
            self.section_controls[section].SetValue("Open this tab to load section data.")

    def _render_overview_section(self) -> None:
        if not self.session.is_loaded:
            return

        overview = {
            "filename": self.session.filename,
            "map_size": self.session.data.get("general", {}).get("map_size"),
            "has_underground": self.session.data.get("general", {}).get("has_underground"),
            "objects": len(self.session.data.get("object_data", [])),
            "object_defs": len(self.session.data.get("object_defs", [])),
        }
        self.section_controls["__overview__"].SetValue(_as_json(overview))
        self._loaded_section_pages.add("__overview__")

    def _ensure_active_section_rendered(self, page_index: int) -> None:
        if not self.session.is_loaded:
            return

        section = self._section_page_by_index.get(page_index)
        if section is None or section == "__overview__":
            return
        if section in self._loaded_section_pages:
            return

        section_data = self.session.data.get(section, "Section not available")
        self.section_controls[section].SetValue(_as_json(section_data))
        self._loaded_section_pages.add(section)

    def _render_minimap_preview(self) -> None:
        if not self.session.is_loaded or self._minimap_bitmap is None:
            return

        image = render_minimap_preview(
            self.session.data,
            mode=self._selected_minimap_mode(),
            selected_layers=self._selected_extended_layers(),
            output_size=self._minimap_render_base_size(),
            gap_size=self._minimap_gap_size,
        )
        self._minimap_cached_image = image
        self._refresh_minimap_display_only()

    def _refresh_minimap_display_only(self) -> None:
        if self._minimap_bitmap is None or self._minimap_cached_image is None:
            return

        image = self._fit_minimap_to_container(self._minimap_cached_image)
        bitmap = _pil_to_wx_bitmap(image)
        self._minimap_bitmap_container.Freeze()
        self._minimap_bitmap.SetBitmap(bitmap)
        # Keep widget size in sync with the bitmap size; otherwise wx clips to the old control bounds.
        self._minimap_bitmap.SetSize(bitmap.GetSize())
        self._place_minimap_bitmap(bitmap.GetSize())
        self._minimap_bitmap_container.Thaw()
        self._minimap_bitmap.Refresh()

    def _place_minimap_bitmap(self, bitmap_size) -> None:
        if self._minimap_bitmap_container is None or self._minimap_bitmap is None:
            return

        container_w, container_h = self._minimap_bitmap_container.GetClientSize()
        if container_w <= 0 or container_h <= 0:
            return

        if isinstance(bitmap_size, tuple):
            bitmap_w, bitmap_h = bitmap_size
        else:
            bitmap_w, bitmap_h = bitmap_size.GetWidth(), bitmap_size.GetHeight()

        x = max(0, (container_w - bitmap_w) // 2)
        y = max(0, (container_h - bitmap_h) // 2)
        self._minimap_bitmap.SetPosition((x, y))

    def _minimap_output_size(self) -> int:
        has_underground = self.session.data.get("general", {}).get("has_underground")
        if self._minimap_bitmap_container is None:
            return 512 if has_underground else 760

        width, height = self._minimap_bitmap_container.GetClientSize()
        if width <= 0 or height <= 0:
            return 512 if has_underground else 760

        if has_underground:
            per_layer = min(height, max(1, (width - self._minimap_gap_size) // 2))
        else:
            per_layer = min(width, height)

        return max(128, min(1400, int(per_layer)))

    def _minimap_render_base_size(self) -> int:
        # Render above display size once, then do lightweight resize-only redraws on window resize.
        return min(1400, max(512, int(self._minimap_output_size() * 1.35)))

    def _fit_minimap_to_container(self, image):
        if self._minimap_bitmap_container is None:
            return image

        container_w, container_h = self._minimap_bitmap_container.GetClientSize()
        if container_w <= 0 or container_h <= 0:
            return image

        img_w, img_h = image.size
        if img_w <= 0 or img_h <= 0:
            return image

        scale = min(container_w / img_w, container_h / img_h)
        target_w = max(1, int(img_w * scale))
        target_h = max(1, int(img_h * scale))

        if target_w == img_w and target_h == img_h:
            return image

        return image.resize((target_w, target_h), resample=PILImage.Resampling.NEAREST)

    def _is_minimap_tab_active(self, selection: int) -> bool:
        return self._minimap_page_index is not None and selection == self._minimap_page_index

    def _selected_minimap_mode(self) -> str:
        if self._minimap_extended_toggle is None or not self._minimap_extended_toggle.GetValue():
            return MINIMAP_STANDARD

        if self._overlay_types_radio is not None and self._overlay_types_radio.GetValue():
            return MINIMAP_EXTENDED_ZONE_TYPES
        if self._overlay_owners_radio is not None and self._overlay_owners_radio.GetValue():
            return MINIMAP_EXTENDED_ZONE_OWNERS
        return MINIMAP_EXTENDED

    def _selected_extended_layers(self) -> list[str]:
        selected = []
        for key, check in self._layer_checks.items():
            if check.GetValue():
                selected.append(key)
        return selected

    def _sync_layer_controls_state(self) -> None:
        extended_mode = self._selected_minimap_mode() != MINIMAP_STANDARD
        if self._overlay_panel is not None:
            self._overlay_panel.Enable(extended_mode)
        if self._layers_panel is not None:
            self._layers_panel.Enable(extended_mode)
        if self._minimap_panel is not None:
            self._minimap_panel.Layout()

    def _update_title(self) -> None:
        suffix = Path(self.session.filename).name if self.session.filename else "No map loaded"
        dirty = " *" if self.session.dirty else ""
        self.SetTitle(f"{App.NAME} - GUI - {suffix}{dirty}")

    def _load_config(self) -> dict[str, Any]:
        """Load config from file, return empty dict if not found."""
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_config(self, config: dict[str, Any]) -> None:
        """Save config to file."""
        try:
            self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def _find_default_maps_directory() -> str:
        """Try to find the Heroes 3 Maps directory from common installation locations."""
        # Try common paths for different platforms
        common_paths = [
            Path("~/Heroes3/Maps").expanduser(),  # Linux home
            Path("~/Library/Application Support/Heroes3/Maps").expanduser(),  # macOS
            Path("~/.h3mex/maps").expanduser(),  # Fallback user directory
            Path("/usr/share/games/Heroes3/Maps"),  # Linux system-wide
            Path("/opt/Heroes3/Maps"),  # Linux alternate
            Path("C:/3DO/Heroes3/Maps"),  # Windows classic
            Path("C:/Program Files/Heroes of Might and Magic III/Maps"),  # Windows
            Path("C:/Program Files (x86)/Heroes of Might and Magic III/Maps"),  # Windows 32-bit
        ]

        for path in common_paths:
            if path.exists() and path.is_dir():
                return str(path)

        # Fall back to repo's maps directory
        repo_root = Path(__file__).resolve().parents[2]
        maps_dir = repo_root / "maps"
        return str(maps_dir if maps_dir.exists() else repo_root)

    def _get_maps_directory(self) -> str:
        """Get the maps directory from config or prompt the user to select it."""
        config = self._load_config()

        # If maps_dir is already configured, return it
        if "maps_dir" in config:
            maps_dir = Path(config["maps_dir"])
            if maps_dir.exists() and maps_dir.is_dir():
                return str(maps_dir)

        # Try to find a default maps directory
        default_dir = self._find_default_maps_directory()

        # Show a dialog asking the user to select or confirm the maps directory
        with wx.DirDialog(
            self,
            "Select your Heroes 3 Maps directory",
            defaultPath=default_dir,
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                selected_dir = dialog.GetPath()
                config["maps_dir"] = selected_dir
                self._save_config(config)
                return selected_dir

        # If cancelled, return the default
        return default_dir

    def on_change_maps_directory(self, _event: wx.CommandEvent) -> None:
        """Handle the Settings > Maps Directory menu item."""
        current_dir = self._current_dir
        with wx.DirDialog(
            self,
            "Select your Heroes 3 Maps directory",
            defaultPath=current_dir,
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                new_dir = dialog.GetPath()
                self._current_dir = new_dir
                config = self._load_config()
                config["maps_dir"] = new_dir
                self._save_config(config)
                wx.MessageBox(
                    f"Maps directory changed to:\n{new_dir}",
                    "Maps Directory Updated",
                    wx.OK | wx.ICON_INFORMATION,
                )


def _load_map_worker(filepath: str, progress_queue: Any) -> None:
    try:

        def progress_callback(message: str) -> None:
            progress_queue.put(("progress", message))

        data = load_map(filepath, progress_callback=progress_callback)
        progress_queue.put(("result", data))
    except Exception as exc:  # noqa: BLE001
        progress_queue.put(("error", str(exc)))


class H3MexGuiApp(wx.App):
    def OnInit(self) -> bool:  # noqa: N802
        frame = MainFrame()
        frame.Show(True)
        self.SetTopWindow(frame)
        return True


def _bytes_encoder(obj: Any) -> str:
    if isinstance(obj, bytes):
        return obj.decode("latin-1")
    raise TypeError(f"Type not serializable: {type(obj)}")


def _as_json(data: Any) -> str:
    return json.dumps(data, default=_bytes_encoder, indent=2)


def _pil_to_wx_bitmap(image) -> wx.Bitmap:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    return wx.Bitmap.FromBufferRGBA(width, height, bytes(rgba.tobytes()))


def run(initial_file: str | None = None) -> None:
    app = H3MexGuiApp(False)
    top = app.GetTopWindow()
    if initial_file and isinstance(top, MainFrame):
        top._load_file(initial_file)
    app.MainLoop()
