"""
Make Light Presets V 1.2 - Community Drop-In Extension By Elvaerwyn_MH2 2026
Allows sharing, loading, and refreshing custom lighting setup profiles natively
"""

import os
import json
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, 
                             QListWidget, QListWidgetItem, QPushButton, QLabel, 
                             QApplication, QMainWindow, QCheckBox, QDockWidget,
                             QInputDialog, QMessageBox, QComboBox, QDialog, 
                             QFormLayout, QDialogButtonBox, QLineEdit, QGroupBox, QSlider)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QVector4D, QPalette, QBrush

class SavePresetMetadataDialog(QDialog):
    """Custom input workspace window allowing manual entry of profile metadata."""
    def __init__(self, parent_widget, default_name=""):
        super().__init__(parent_widget)
        self.setWindowTitle("Save Master Lighting Setup")
        self.resize(380, 200)
        self.setPalette(parent_widget.palette())
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit(default_name)
        self.author_input = QLineEdit("Elvaerwyn_Community")
        self.notes_input = QLineEdit("Custom studio setup.")
        
        form_layout.addRow("Preset Profile Name:", self.name_input)
        form_layout.addRow("Author / Creator:", self.author_input)
        form_layout.addRow("Pipeline Notes:", self.notes_input)
        layout.addLayout(form_layout)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def get_metadata(self):
        return {
            "name": self.name_input.text().strip(),
            "author": self.author_input.text().strip(),
            "notes": self.notes_input.text().strip()
        }

class CommunityLightPresetPanel(QWidget):
    """The master layout widget handling folder scans, selection clicks, and dock-locking."""
    def __init__(self,  app_reference, glob_reference, pluginname):
        self.glob = glob_reference
        self.main_window = self.glob.MainWindow
        self.mh_app = app_reference
        self.pluginname = pluginname
        super().__init__(self.glob.MainWindow)
        
        self.view = self.glob.openGLWindow
        self.env = self.glob.env
        self.light_sys = self.view.light
        self.scene_sys = self.view.scene
        
        # presets can be saved, so it will be sys_presets_dir and user_presets_dir
        #
        self.current_dir = os.path.dirname(pluginname)
        self.sys_presets_dir = self.glob.env.fullPath(os.path.join(self.current_dir, "lighting_presets"))
        self.user_presets_dir = self.glob.env.fullPath(os.path.join(self.glob.env.stdUserPath(), "lighting_presets"))

        # Build out lookups dynamically inside the isolated extension directory
        self.gobos_dir = os.path.normpath(os.path.join(self.current_dir, "light_gobos")).replace("\\", "/")
        if not os.path.exists(self.gobos_dir):
            try: os.makedirs(self.gobos_dir)
            except Exception: pass

        self.luts_dir = os.path.normpath(os.path.join(self.current_dir, "light_luts")).replace("\\", "/")
        if not os.path.exists(self.luts_dir):
            try: os.makedirs(self.luts_dir)
            except Exception: pass

        self.scanned_presets = {}
        self.repo = self.glob.pluginRepo
        self.dock = None
        self.panel = None

        self.tracking_timer = None
        self.fx_math_timer = None
        self.pause = False

    class Panel(QWidget):
        def __init__(self, parent):
            super().__init__()

            self.parent = parent
            layout = QVBoxLayout(self)
            layout.setSpacing(6)
            layout.setContentsMargins(8, 8, 8, 8)

            self.dock_status_banner = QLabel("📌 Status: Docked (Drag header out to float)")
            self.dock_status_banner.setAlignment(Qt.AlignCenter)
            self.dock_status_banner.setWordWrap(True)
            self.dock_status_banner.setMinimumHeight(28)
            self.dock_status_banner.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    border: 1px solid rgba(128, 128, 128, 60);
                    border-radius: 3px;
                    padding: 4px;
                    background-color: rgba(128, 128, 128, 15);
                }
            """)
            layout.addWidget(self.dock_status_banner)

            self.lock_layout_toggle = QCheckBox("🔒 Lock Preset Panel Dock Frame")
            self.lock_layout_toggle.setChecked(False)
            self.lock_layout_toggle.stateChanged.connect(parent.toggle_panel_dock_lock)
            layout.addWidget(self.lock_layout_toggle)

            layout.addWidget(QLabel("<b>Available Community Style Presets:</b>"))
        
            self.preset_list = QListWidget()
            self.preset_list.itemDoubleClicked.connect(parent.execute_selected_preset)
            layout.addWidget(self.preset_list)
        
            # FX Dropdowns configuration layout form
            fx_layout = QFormLayout()
            fx_layout.setSpacing(4)
        
            self.gobo_picker = QComboBox()
            self.gobo_picker.addItem("❌ No Decal Mask", "none")
            # Added explicit procedural gobo profiles to match math loop conditions
            self.gobo_picker.addItem("🌊 Algorithmic Wave Bands", "wave")
            self.gobo_picker.addItem("🏁 Grid Coordinate Mask", "grid")
            fx_layout.addRow("Procedural Math Gobo:", self.gobo_picker)
        
            self.lut_picker = QComboBox()
            self.lut_picker.addItem("❌ No Grading LUT", "none")
            # Added explicit procedural grading profiles to pass conditions
            self.lut_picker.addItem("🔥 Warm Amber Grade", "warm")
            fx_layout.addRow("Procedural Math LUT:", self.lut_picker)
        
            self.procedural_picker = QComboBox()
            self.procedural_picker.addItem("❌ No Math Routine", "none")
            self.procedural_picker.addItem("🎉 Rainbow Confetti Shimmer", "confetti_shimmer")
            self.procedural_picker.addItem("🌊 Water Ripple Cavern Sine", "water_ripple")
            self.procedural_picker.addItem("🪩 Mirror Disco Ball Rotation", "disco_ball")
            self.procedural_picker.addItem("💎 Window Crystal Prism Rainbow", "crystal_prism")
            self.procedural_picker.addItem("🦋 Classic Butterfly Portrait", "butterfly")
            self.procedural_picker.addItem("▫️ Flat Shadowless Fill", "flat_fill")
            self.procedural_picker.addItem("😇 Perimeter Rim Halo Glow", "rim_halo")
            self.procedural_picker.addItem("🌋 Skyroom Cubemap Shift", "skyroom_shift")

            # FIXED: Registered new organic fluid and fire flickering math keys into the UI menu
            self.procedural_picker.addItem("🧪 Psychedelic Lava Lamp Blobs", "lava_lamp")
            self.procedural_picker.addItem("🕯️ Erratic Candlelight Flicker", "candle_flicker")
            fx_layout.addRow("Procedural Math FX:", self.procedural_picker)
        
            # FIXED: Added the Amount menu mapping value string configurations accurately
            self.amount_picker = QComboBox()
            for i in range(1, 11):
                self.amount_picker.addItem(f"📊 Level Setting: {i}", str(i))
            self.amount_picker.setCurrentIndex(4) # Default value setting is 5
            fx_layout.addRow("FX Amount Preset (1-10):", self.amount_picker)

            # NEW: Added a PC Performance optimization selector
            self.hardware_picker = QComboBox()
            self.hardware_picker.setToolTip("Optimize math calculation speeds based on your system hardware.")
            self.hardware_picker.addItem("💻 Balanced PC Profile (30 FPS Standard)", "balanced")
            self.hardware_picker.addItem("🥔 Low-End PC / Laptop Profile (Battery & CPU Safe)", "low_end")
            self.hardware_picker.addItem("🚀 High-End Gaming PC Profile (Ultra-Smooth 60 FPS)", "high_end")
            self.hardware_picker.setCurrentIndex(0) # Default to Balanced
            fx_layout.addRow("Hardware Optimization:", self.hardware_picker)
        
            # Connect it so changing the PC profile updates the timer speed instantly
            self.hardware_picker.currentIndexChanged.connect(parent.toggle_procedural_math_engine)


            self.gobo_picker.currentIndexChanged.connect(parent.apply_selected_gobo_decal)
            self.lut_picker.currentIndexChanged.connect(parent.apply_selected_lut_profile)
            self.procedural_picker.currentIndexChanged.connect(parent.toggle_procedural_math_engine)
            layout.addLayout(fx_layout)

            btn_layout = QHBoxLayout()
            # CRITICAL UPGRADE: Reset Engine Button row to clear active FX wrappers completely
            self.clear_fx_btn = QPushButton("🛑 Deactivate Overrides & Clear Active FX")
            self.clear_fx_btn.setToolTip("Instantly remove math gobos, disable look-up matrices, disable skin shading overrides, and reset math engine calculations.")
            self.clear_fx_btn.setStyleSheet("color: rgba(220, 53, 69, 255)")
            self.clear_fx_btn.clicked.connect(parent.deactivate_all_fx_overrides)
            btn_layout.addWidget(self.clear_fx_btn)
            self.toggle_effects = QPushButton()
            self.setPauseText()
            self.toggle_effects.setToolTip("Pause effects / Resume effects")
            self.toggle_effects.clicked.connect(parent.pause_or_resume)
            btn_layout.addWidget(self.toggle_effects)
            layout.addLayout(btn_layout)
        
            # Scan folders to retain backwards file support for legacy assets
            if os.path.isdir(parent.gobos_dir):
                for filename in os.listdir(parent.gobos_dir):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        self.gobo_picker.addItem(f"🖼️ File: {filename}", filename)

            if os.path.isdir(parent.luts_dir):
                for filename in os.listdir(parent.luts_dir):
                    if filename.lower().endswith(('.png', '.cube', '.jpg')):
                        self.lut_picker.addItem(f"🎨 File: {filename}", filename)

            # SHADER COMPLIANCE BLOCK
            cam_group = QGroupBox("🎥 Studio Light Focus, Shaders & Falloff")
            cam_layout = QFormLayout(cam_group)
            cam_layout.setSpacing(6)

            self.harsh_light_toggle = QCheckBox("Enable Sharp Directional Key Lighting")
            self.harsh_light_toggle.setChecked(False)
            self.harsh_light_toggle.stateChanged.connect(parent.apply_cinematic_fx_to_viewport)
            cam_layout.addRow("Harsh Light Ray:", self.harsh_light_toggle)

            self.blinn_toggle = QCheckBox("Use Soft Blinn-Phong Skin Reflections")
            self.blinn_toggle.setChecked(False)
            self.blinn_toggle.stateChanged.connect(parent.apply_cinematic_fx_to_viewport)
            cam_layout.addRow("Blinn Shading:", self.blinn_toggle)

            self.toon_toggle = QCheckBox("Enable Math LitSphere Cel-Shading")
            self.toon_toggle.setChecked(False)
            self.toon_toggle.stateChanged.connect(parent.apply_cinematic_fx_to_viewport)
            cam_layout.addRow("Toon LitSphere Shading:", self.toon_toggle)

            self.specular_slider = QSlider(Qt.Horizontal)
            self.specular_slider.setRange(1, 128)
            self.specular_slider.setValue(32)
            self.specular_slider.valueChanged.connect(parent.apply_cinematic_fx_to_viewport)
            cam_layout.addRow("Material Specular Focus:", self.specular_slider)

            layout.addWidget(cam_group)

            btn_layout = QHBoxLayout()
            load_btn = QPushButton("🔵 Load Selected Profile")
            load_btn.clicked.connect(parent.execute_button_click_load)
            btn_layout.addWidget(load_btn)
        
            refresh_btn = QPushButton("🔄 Refresh Catalog")
            refresh_btn.clicked.connect(parent.scan_presets_folder)
            btn_layout.addWidget(refresh_btn)
        
            save_btn = QPushButton("🟢 Capture Setup")
            save_btn.clicked.connect(parent.capture_and_save_active_preset)
            btn_layout.addWidget(save_btn)

            self.delete_btn = QPushButton("❌ Delete")
            self.delete_btn.clicked.connect(parent.delete_selected_preset)
            btn_layout.addWidget(self.delete_btn)
            layout.addLayout(btn_layout)
        
            self.original_scene_backup = None

        def setPauseText(self):
            t = ["Pause", "Resume"]
            self.toggle_effects.setText(t[(int(self.parent.pause))])

    def establish_dock_signal_tracking_hooks(self):
        """Safely hooks into the parent frame wrappers to monitor dragging states."""
        dock_widget = self.parentWidget()
        while dock_widget and not isinstance(dock_widget, QDockWidget):
            dock_widget = dock_widget.parentWidget()
            
        if dock_widget:
            dock_widget.topLevelChanged.connect(self.refresh_visual_dock_status_string)
            dock_widget.dockLocationChanged.connect(lambda area: self.refresh_visual_dock_status_string())
            self.refresh_visual_dock_status_string()

    def refresh_visual_dock_status_string(self):
        """Updates the top banner text dynamically to guide user floating operations."""
        dock_widget = self.parentWidget()
        while dock_widget and not isinstance(dock_widget, QDockWidget):
            dock_widget = dock_widget.parentWidget()
            
        if dock_widget:
            if dock_widget.isFloating():
                self.dock_status_banner.setText("💡 Double-Click Top Window Frame to instantly auto-dock")
                self.dock_status_banner.setStyleSheet("""
                    QLabel {
                        font-weight: bold;
                        border: 1px dashed #3A7DDEC0;
                        border-radius: 3px;
                        padding: 4px;
                        background-color: rgba(58, 125, 222, 25);
                    }
                """)
            else:
                if dock_widget.features() == QDockWidget.NoDockWidgetFeatures:
                    self.dock_status_banner.setText("🔒 Status: LOCKED & STATIC inside sidebar workspace")
                else:
                    self.dock_status_banner.setText("📌 Status: Docked (Drag panel header to float)")
                self.dock_status_banner.setStyleSheet("""
                    QLabel {
                        font-weight: bold;
                        border: 1px solid rgba(128, 128, 128, 60);
                        border-radius: 3px;
                        padding: 4px;
                        background-color: rgba(128, 128, 128, 15);
                    }
                """)

    def toggle_panel_dock_lock(self, state):
        """Freezes the layout frame dynamically using chosen lock behavior."""
        dock_widget = self.parentWidget()
        while dock_widget and not isinstance(dock_widget, QDockWidget):
            dock_widget = dock_widget.parentWidget()

        if dock_widget:
            if state == 2:  
                dock_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
                self.lock_layout_toggle.setText("🔒 Preset Panel Dock Frame LOCKED")
            else:          
                dock_widget.setFeatures(
                    QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
                )
                self.lock_layout_toggle.setText("🔓 Lock Preset Panel Dock Frame")

    def capture_original_scene_snapshot(self):
        """Silently caches the user's exact light rig before any overrides touch it."""
        # Only take a snapshot if we don't have one already (prevents overwriting the backup)
        if self.original_scene_backup is not None:
            return
            
        try:
            lights_collection = self.light_sys.lights if hasattr(self.light_sys, 'lights') else []
            backup_lights = []
            
            # Map out every live light property
            if isinstance(lights_collection, list):
                for idx, elem in enumerate(lights_collection):
                    # Safely handle vector coordinate unpacking
                    raw_vol = elem.get("vol", [1.0, 1.0, 1.0])
                    l_color = [raw_vol.x(), raw_vol.y(), raw_vol.z()] if hasattr(raw_vol, 'x') else list(raw_vol[:3])
                    
                    raw_pos = elem.get("pos", [0.0, 5.0, 0.0])
                    l_pos = [raw_pos.x(), raw_pos.y(), raw_pos.z()] if hasattr(raw_pos, 'x') else list(raw_pos[:3])
                    
                    backup_lights.append({
                        "id": idx,
                        "type": elem.get("type", 1),
                        "luminance": float(elem.get("int", 5.0)),
                        "color": l_color,
                        "position": l_pos,
                        "height": float(elem.get("h", 5.0)) if hasattr(self.light_sys, 'setHPos') else 5.0
                    })
            
            # Pack the entire room baseline together
            self.original_scene_backup = {
                "lights": backup_lights,
                "harsh_key_light": self.panel.harsh_light_toggle.isChecked(),
                "use_blinn_shading": self.panel.blinn_toggle.isChecked(),
                "use_toon_shading": self.panel.toon_toggle.isChecked(),
                "material_specular_focus": self.panel.specular_slider.value()
            }
            self.glob.env.logLine(2, "[Preset Engine] Original lighting setup securely cached in memory.")
        except Exception as e:
            self.glob.env.logLine(1, f"[Preset Engine Warning] Failed to cache user's scene state: {str(e)}")

    def apply_cinematic_fx_to_viewport(self):
        """Passes specular focus boundaries and shading loops straight to the pipeline."""
        if not self.view or not self.light_sys:
            return
            
        # 1. NATIVE REFLECTION ASSIGNMENT
        self.light_sys.blinn = self.panel.blinn_toggle.isChecked()

        # 2. LIGHT TYPE SWITCHER, switch first of the 3 lights
        is_directional = self.panel.harsh_light_toggle.isChecked()
        self.light_sys.lights[0]["type"] = 0 if is_directional else 1
                
        # specularFocus is placed in Y value
        gloss_factor = float(self.panel.specular_slider.value())
        self.light_sys.lightWeight.setY(gloss_factor)
        self.light_sys.setShader()

        # 4. FORCE REPAINT UPDATE (Tweak includes update)
        self.view.Tweak()
                
    def create_presets_directories(self):
        """
        we do that only on tool startup
        """
        if not os.path.exists(self.sys_presets_dir):
            try: os.makedirs(self.sys_presets_dir)
            except Exception: pass

        if not os.path.exists(self.user_presets_dir):
            try: os.makedirs(self.user_presets_dir)
            except Exception: pass

    def scan_presets_folder(self):
        self.panel.preset_list.clear()
        self.scanned_presets.clear()
        
        for predir in (self.sys_presets_dir, self.user_presets_dir):
            if os.path.isdir(predir):
                for filename in os.listdir(predir):
                    if filename.lower().endswith('.json'):
                        full_path = os.path.join(predir, filename).replace("\\", "/")
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                self.scanned_presets[filename] = data
                            
                                name = data.get("preset_name", filename)
                                item = QListWidgetItem(f"💡 {name} (by {data.get('author', 'Community')})")
                                item.setData(Qt.UserRole, filename)
                                self.panel.preset_list.addItem(item)
                        except Exception:
                            pass

    def execute_button_click_load(self):
        """Passes the highlighted row selection directly into the execution track."""
        selected_item = self.panel.preset_list.currentItem()
        if not selected_item:
            QMessageBox.warning(
                self, "No Selection", 
                "Please click a profile row from the library catalog list first before clicking Load."
            )
            return
        self.execute_selected_preset(selected_item)

    def execute_selected_preset(self, item):
        if not item: 
            return
        filename_key = item.data(Qt.UserRole)
        config = self.scanned_presets.get(filename_key)
        if not config: 
            return

        try:
            if "ambient_luminance" in config:
                self.light_sys.setAmbientLuminance(float(config["ambient_luminance"]) / 100.0)
            if "ambient_color" in config:
                ac = config["ambient_color"]
                if isinstance(ac, (list, tuple)) and len(ac) >= 3:
                    self.light_sys.setAmbientColor(QColor.fromRgbF(*ac[:3]))
                    if hasattr(self.light_sys, 'ambientColorList'):
                        self.light_sys.ambientColorList = list(ac[:3])
                
            if "clear_color" in config:
                cc = config["clear_color"]
                if isinstance(cc, (list, tuple)) and len(cc) >= 3:
                    self.light_sys.setClearColor(QColor.fromRgbF(*cc[:3]))
                else:
                    self.light_sys.setClearColor(QColor.fromRgbF(float(cc), float(cc), float(cc)))

            if "floor_size" in config:
                self.scene_sys.setFloorSize(int(config["floor_size"]))
                
            if "floor_texture" in config:
                self.scene_sys.modFloorTexture(str(config["floor_texture"]))

            if "lights" in config:
                for l_data in config["lights"]:
                    l_idx = int(l_data.get("id", 0))
                    if l_idx >= len(self.light_sys.lights): 
                        continue
                    
                    self.light_sys.setLLuminance(l_idx, float(l_data.get("luminance", 5.0)))
                    
                    lc = l_data.get("color", [1.0, 1.0, 1.0])
                    if isinstance(lc, (list, tuple)) and len(lc) >= 3:
                        self.light_sys.setLColor(l_idx, QColor.fromRgbF(*lc[:3]))
                    else:
                        self.light_sys.setLColor(l_idx, QColor.fromRgbF(1.0, 1.0, 1.0))
                    
                    self.light_sys.setType(l_idx, int(l_data.get("type", 1)))

                    pos = l_data.get("position", [0.0, 5.0, 0.0])
                    if isinstance(pos, (list, tuple)) and len(pos) >= 3:
                        raw_x = float(pos[0])
                        raw_y = float(pos[1])
                        raw_z = float(pos[2])
                        
                        self.light_sys.setLPos(l_idx, raw_x, raw_z)
                        self.light_sys.setHPos(l_idx, raw_y)
                    else:
                        self.light_sys.setLPos(l_idx, 0.0, 0.0)
                        self.light_sys.setHPos(l_idx, 5.0)

            # Safely sync studio interface values whenever a preset is double-clicked
            self.panel.harsh_light_toggle.setChecked(config.get("harsh_key_light", False))
            self.panel.blinn_toggle.setChecked(config.get("use_blinn_shading", False))
            self.panel.toon_toggle.setChecked(config.get("use_toon_shading", False))
            self.panel.specular_slider.setValue(int(config.get("material_specular_focus", 32)))
            
            self.apply_cinematic_fx_to_viewport()
            self.view.Tweak()
            self.glob.env.logLine(1, f"[Make Light, Preset Engine] Successfully ran style footprint: {config.get('preset_name')}")
            
        except Exception as e:
            self.glob.env.logLine(1, f"[Make Light, Preset Engine Error] Runtime setup failure: {str(e)}")

    def apply_selected_gobo_decal(self):
        """Passes algorithmic projection configurations to the mesh calculation loops."""
        gobo_mode = self.panel.gobo_picker.currentData()
        self.glob.env.logLine(2, f"[Make Light, Preset FX] Gobo processing profile swapped to math matrix: {gobo_mode}")
        self.view.Tweak()

    def apply_selected_lut_profile(self):
        """Engages numerical camera lookup grading layers inside the drawing track."""
        lut_mode = self.panel.lut_picker.currentData()
        self.glob.env.logLine(2, f"[Make Light, Preset FX] Color calibration grading offset applied: {lut_mode}")
        self.view.Tweak()

    def delete_fx_math_timer(self):
        if self.fx_math_timer is not None:
            self.fx_math_timer.stop()
            self.fx_math_timer = None

    def stop_fx_math_timer(self):
        if self.fx_math_timer is not None:
            self.fx_math_timer.stop()

    def start_fx_math_timer(self):
        if self.fx_math_timer is not None:
            self.fx_math_timer.start()

    def stop_tracking_timer(self):
        if self.tracking_timer is not None:
            self.tracking_timer.stop()

    def start_tracking_timer(self):
        if self.tracking_timer is not None:
            self.tracking_timer.start()

    def deactivate_all_fx_overrides(self):
        """CRITICAL MASTER RESET: Unlocks all persistent states, stops loops, and clears hooks instantly."""
        self.glob.env.logLine(1, "[Make Light, Preset Engine] Commencing FX deactivation sequence...")
        try:
            # 1. Stop background math engines completely
            self.panel.procedural_picker.setCurrentIndex(0)
            self.delete_fx_math_timer()
            
            # 2. Reset combo boxes to baseline indices
            self.panel.gobo_picker.setCurrentIndex(0)
            self.panel.lut_picker.setCurrentIndex(0)
            
            # 3. Drop layout checkboxes back to standard definitions
            self.panel.harsh_light_toggle.setChecked(False)
            self.panel.blinn_toggle.setChecked(False)
            self.panel.toon_toggle.setChecked(False)
            self.panel.specular_slider.setValue(32)
            
            # 4. Push clean baseline states across view controllers
            self.apply_cinematic_fx_to_viewport()
            self.view.Tweak()
            self.glob.env.logLine(1, "[Make Light, Preset Engine] Active FX profiles dismantled. Viewport restored to studio baseline configuration.")
        except Exception as err:
            self.glob.env.logLine(1, f"[Make Light, Preset Engine Error] Deactivation loop dropped a property assignment fault: {str(err)}")


    def pause_or_resume(self):
        if self.pause is False:
            self.stop_fx_math_timer()
            self.stop_tracking_timer()
        else:
            self.start_fx_math_timer()
            self.start_tracking_timer()
        self.pause = not self.pause
        self.panel.setPauseText()

    def toggle_procedural_math_engine(self):
        """Main calculation routine managing frame rendering parameters over time."""
        routine = self.panel.procedural_picker.currentData()
        
        # Define an explicit instance loop target to guarantee clean disconnect tracks
        if self.fx_math_timer is None:
            self.fx_math_timer = QTimer(self)
            self.fx_math_frame_counter = 0.0
            self._current_active_slot = None
            
        # Strict manual function token verification prevents connection stacking freezes
        if self._current_active_slot is not None:
            try:
                self.fx_math_timer.timeout.disconnect(self._current_active_slot)
            except Exception:
                pass
            self._current_active_slot = None

        if routine == "none" and not self.panel.gobo_picker.currentData() != "none" and not self.panel.lut_picker.currentData() != "none" and not self.panel.toon_toggle.isChecked():
            self.stop_fx_math_timer()
            self.glob.env.logLine(2, "[Make Light, Preset FX] Procedural math engine completely disconnected and freed.")
            return
            
        def run_math_frame_calculations():
            self.fx_math_frame_counter += 0.05
            speed = self.fx_math_frame_counter
            
            # FIXED: Safe type conversion that defaults to 5 if the widget data drops a string formatting fault
            try:
                raw_level = self.panel.amount_picker.currentData()
                intensity_scale = float(raw_level) if raw_level else 5.0
            except (TypeError, ValueError):
                intensity_scale = 5.0

            # Turn 1-10 into an explicit scaling range multiplier (e.g. Level 1 = 0.1, Level 10 = 2.0)
            fx_multiplier = intensity_scale / 5.0
            
            try:
                lights_collection = self.light_sys.lights if hasattr(self.light_sys, 'lights') else []
                total_lights = len(lights_collection) if isinstance(lights_collection, list) else 0

                # =========================================================================
                # PASS A: PROCEDURAL MATH ATMOSPHERES (Now driven by fx_multiplier)
                # =========================================================================
                if routine == "confetti_shimmer" and total_lights > 0:
                    for idx in range(total_lights):
                        # Multiplier controls color vibrancy and saturation depth limits
                        r = (np.sin(speed + idx) * fx_multiplier + 1.0) / 2.0
                        g = (np.sin(speed * 1.5 + idx) * fx_multiplier + 1.0) / 2.0
                        b = (np.cos(speed * 0.8 + idx) * fx_multiplier + 1.0) / 2.0
                        self.light_sys.setLColor(idx, QColor.fromRgbF(np.clip(r,0,1), np.clip(g,0,1), np.clip(b,0,1)))
                
                elif routine == "water_ripple" and total_lights > 0:
                    # Multiplier controls the raw wave height/intensity of the ripple
                    ripple = np.sin(speed * 3.0) * (1.2 * fx_multiplier)
                    self.light_sys.setLLuminance(0, float(4.5 + ripple))
                
                elif routine == "disco_ball" and total_lights > 0:
                    for idx in range(total_lights):
                        offset = idx * (2.0 * np.pi / max(1, total_lights))
                        # Multiplier controls how wide the lights rotate around the room!
                        x_rot = np.sin(speed * 2.0 + offset) * (7.5 * fx_multiplier)
                        z_rot = np.cos(speed * 2.0 + offset) * (7.5 * fx_multiplier)
                        h_rot = 4.5 + np.sin(speed * 0.7) * (1.8 * fx_multiplier)
                        
                        self.light_sys.setLPos(idx, float(x_rot), float(z_rot))
                        self.light_sys.setHPos(idx, float(h_rot))
                        
                        r_hue = (np.sin(speed * 3.0 + idx) + 1.0) / 2.0
                        g_hue = (np.cos(speed * 2.1 + idx) + 1.0) / 2.0
                        b_hue = (np.sin(speed * 4.2 + idx) + 1.0) / 2.0
                        self.light_sys.setLColor(idx, QColor.fromRgbF(r_hue, g_hue, b_hue))
                        self.light_sys.setLLuminance(idx, float(5.5 + np.sin(speed * 5.0) * 2.5))

                
                elif routine == "crystal_prism" and total_lights > 0:
                    for idx in range(total_lights):
                        dispersion_angle = idx * 0.65
                        r_ray = (np.sin(speed * 0.4 + dispersion_angle) + 1.0) / 2.0
                        g_ray = (np.sin(speed * 0.4 + dispersion_angle + 2.0) + 1.0) / 2.0
                        b_ray = (np.sin(speed * 0.4 + dispersion_angle + 4.0) + 1.0) / 2.0
                        
                        self.light_sys.setLColor(idx, QColor.fromRgbF(r_ray, g_ray, b_ray))
                        self.light_sys.setLLuminance(idx, float(3.8 + np.sin(speed * 1.2 + idx) * 0.9))

                elif routine == "lava_lamp" and total_lights > 0:
                    for idx in range(total_lights):
                        # Level scales the physical vertical height of the floating blobs
                        drift = np.sin(speed * 0.6 + idx * 1.5)
                        h_pos = 5.0 + (drift * 3.0 * intensity_scale)
                        x_pos = np.cos(speed * 0.3 + idx) * 2.0
                        
                        self.light_sys.setHPos(idx, float(h_pos))
                        self.light_sys.setLPos(idx, float(x_pos), 0.0)
                        
                        r_magma = (np.sin(speed * 0.5 + idx) + 1.0) / 2.0
                        g_magma = (np.cos(speed * 0.3) + 1.0) / 4.0
                        b_magma = (np.cos(speed * 0.4 + idx) + 1.0) / 2.0
                        
                        self.light_sys.setLColor(idx, QColor.fromRgbF(r_magma, g_magma, b_magma))
                        self.light_sys.setLLuminance(idx, float(4.0 + np.sin(speed * 0.8) * 1.0))

                elif routine == "candle_flicker" and total_lights > 0:
                    for idx in range(total_lights):
                        # Level scales the severity of the fire draft stutter noise
                        draft_noise = ((np.sin(speed * 12.0) * 0.4) + (np.sin(speed * 27.0) * 0.25)) * intensity_scale
                        
                        r_fire = 1.0
                        g_fire = np.clip(0.55 + draft_noise * 0.1, 0.4, 0.7)
                        b_fire = np.clip(0.10 + draft_noise * 0.05, 0.0, 0.2)
                        
                        self.light_sys.setHPos(idx, float(4.8 + draft_noise * 0.15))
                        self.light_sys.setLColor(idx, QColor.fromRgbF(r_fire, g_fire, b_fire))
                        
                        candle_lux = 3.5 + draft_noise * 2.2
                        self.light_sys.setLLuminance(idx, float(max(0.5, candle_lux)))

                # =========================================================================
                # PASS A1: ADVANCED COMPOSITING ATMOSPHERES & CORE STUDIO RIGS
                # =========================================================================
                if routine == "butterfly" and total_lights > 0:
                    # BUTTERFLY RIG: Position light 0 directly center-front, high altitude
                    self.light_sys.setLPos(0, 0.0, -2.0)  # Locked straight on front axis
                    self.light_sys.setHPos(0, 9.5)        # High elevation downward angle
                    self.light_sys.setLLuminance(0, float(7.0 * fx_multiplier))
                    self.light_sys.setLColor(0, QColor.fromRgbF(1.0, 0.95, 0.90)) # Warm studio white
                    
                    # Drop extra fills to zero or low accent ambient levels to maximize nose shadow tracking
                    for idx in range(1, total_lights):
                        self.light_sys.setLLuminance(idx, float(0.5))

                elif routine == "flat_fill" and total_lights > 0:
                    # FLAT RIG: Distribute illumination vectors symmetrically to completely cancel contours
                    for idx in range(total_lights):
                        angle = idx * (2.0 * np.pi / max(1, total_lights))
                        x_pos = np.sin(angle) * 6.0
                        z_pos = np.cos(angle) * 6.0
                        
                        self.light_sys.setLPos(idx, float(x_pos), float(z_pos))
                        self.light_sys.setHPos(idx, 4.0)  # Level camera plane height
                        self.light_sys.setLLuminance(idx, float(4.0 * fx_multiplier))
                        self.light_sys.setLColor(idx, QColor.fromRgbF(0.95, 0.95, 1.0)) # Soft daylight fill

                elif routine == "rim_halo" and total_lights > 0:
                    # RIM RIG: Drive primary units behind the target mesh facing straight forward toward camera
                    for idx in range(total_lights):
                        offset = idx * 0.3
                        # Place points tightly clustered deep in the background plane facing inward
                        x_rim = np.sin(speed + offset) * 1.5
                        z_rim = 8.5  # Fixed back placement position
                        
                        self.light_sys.setLPos(idx, float(x_rim), float(z_rim))
                        self.light_sys.setHPos(idx, float(5.0 + np.cos(speed) * 1.2))
                        
                        # Generate intense, cold highlighting glow color states
                        self.light_sys.setLLuminance(idx, float(9.0 * fx_multiplier))
                        self.light_sys.setLColor(idx, QColor.fromRgbF(0.8, 0.9, 1.0))

                elif routine == "skyroom_shift" and total_lights > 0:
                    # SKYROOM PROJECTOR: Modulates background clear colors and light properties together
                    cycle_val = speed * 0.5
                    r_sky = (np.sin(cycle_val) + 1.0) / 2.0
                    g_sky = (np.sin(cycle_val * 0.7 + 2.0) + 1.0) / 4.0  # Maintain low green weights
                    b_sky = (np.cos(cycle_val * 1.2) + 1.0) / 2.0
                    
                    # 1. Update your viewport's ambient canvas background color directly
                    sky_color = QColor.fromRgbF(r_sky * 0.25, g_sky * 0.25, b_sky * 0.25)
                    self.light_sys.setClearColor(sky_color)
                        
                    # 2. Project glowing environment reflection hues onto the lights collection
                    for idx in range(total_lights):
                        self.light_sys.setLColor(idx, QColor.fromRgbF(r_sky, g_sky, b_sky))
                        self.light_sys.setLLuminance(idx, float(4.5 + np.sin(speed * 2.0) * 1.5))

                # =========================================================================
                # PASS B: PROCEDURAL LIGHTSPHERE / GOBO / LUT MATH INJECTIONS
                # =========================================================================
                gobo_active = self.panel.gobo_picker.currentData()
                lut_active = self.panel.lut_picker.currentData()
                toon_active = self.panel.toon_toggle.isChecked()

                if (gobo_active != "none" or lut_active != "none" or toon_active) and total_lights > 0:
                    for idx in range(total_lights):
                        base_color = QColor(255, 255, 255)
                        
                        if toon_active:
                            # Replicate vector space normal alignments
                            nx = np.sin(speed * 0.4 + idx * 0.8)
                            ny = np.cos(speed * 0.5 + idx * 0.8)
                            light_alignment = nx * 0.6 + ny * 0.8
                            
                            # Instant Step Cutoff producing a hyper-sharp ink-like shadow line
                            if light_alignment >= 0.15:
                                r_cell, g_cell, b_cell = 0.85, 0.40, 0.45
                                
                                # Hyper-sharp anime specular point cutoff
                                specular_dot = np.exp(-((nx - 0.25)**2 + (ny - 0.3)**2) / 0.02)
                                if specular_dot > 0.65:
                                    r_cell, g_cell, b_cell = 1.0, 1.0, 1.0
                            else:
                                r_cell, g_cell, b_cell = 0.35, 0.15, 0.22
                                
                            base_color = QColor.fromRgbF(r_cell, g_cell, b_cell)
                        
                        if gobo_active != "none":
                            frequency = 4.0 if gobo_active == "wave" else 8.0
                            # Sharp binary step for the math gobos
                            gobo_mask = 1.0 if (np.sin(speed * 3.0 + idx * frequency) > 0.0) else 0.2
                            base_color = QColor.fromRgbF(
                                base_color.redF() * gobo_mask,
                                base_color.greenF() * gobo_mask,
                                base_color.blueF() * gobo_mask
                            )

                        if lut_active != "none":
                            base_color = QColor.fromRgbF(
                                np.clip(base_color.redF() * 1.15, 0.0, 1.0),
                                np.clip(base_color.greenF() * 0.90, 0.0, 1.0),
                                np.clip(base_color.blueF() * 0.80, 0.0, 1.0)
                            )

                        self.light_sys.setLColor(idx, base_color)

                self.view.Tweak()
            except Exception as e:
                self.glob.env.logLine(1, f"[Make Light, Math Engine Failure] Auto-aborting procedural routine loops: {str(e)}")
                self.stop_fx_math_timer()

        # Cache the current active slot reference before starting the execution tracking loop
        #self._current_active_slot = run_math_frame_calculations
        #self.fx_math_timer.timeout.connect(self._current_active_slot)
        # =========================================================================
        # DYNAMIC HARDWARE SPEED MATRIX (Calculates optimized millisecond delays)
        # =========================================================================
        pc_profile = self.panel.hardware_picker.currentData()
        
        # 1. Establish the baseline framework speeds for the chosen hardware profile
        if pc_profile == "low_end":
            # Low-end profile drastically caps speeds to preserve CPU threads
            base_delay = 66   # Runs standard atmospheres at 15 FPS (Very smooth for Lava Lamp)
            ambient_delay = 100 # Drops slow background cycles down to 10 FPS
            critical_delay = 45 # Keeps critical flicker loops running slightly faster
        elif pc_profile == "high_end":
            # High-end profile juices everything to silky smooth 60 FPS
            base_delay = 16
            ambient_delay = 16
            critical_delay = 16
        else:
            # Balanced standard (30 FPS default)
            base_delay = 33
            ambient_delay = 33
            critical_delay = 33

        # 2. Adjust individual speeds dynamically based on the active routine requirements
        if routine == "candle_flicker":
            # Candle flickers *require* fast stutter physics noise to look realistic
            optimized_ms_delay = critical_delay
        elif routine in ["lava_lamp", "skyroom_shift"]:
            # Slow, fluid rising blobs and color fades look perfectly fine running slower
            optimized_ms_delay = ambient_delay if pc_profile == "low_end" else base_delay
        else:
            optimized_ms_delay = base_delay

        # Cache the current active slot reference and fire up the adaptive clock
        self._current_active_slot = run_math_frame_calculations
        self.fx_math_timer.timeout.connect(self._current_active_slot)
        
        # Turn on the timer using our dynamically calculated hardware speed!
        self.fx_math_timer.start(optimized_ms_delay)
        self.glob.env.logLine(2, f"[Make Light, Preset FX] Math matrix engaged. Optimized loop delay: {optimized_ms_delay}ms ({pc_profile} mode)")


    def capture_and_save_active_preset(self):
        """Launches manual text form processing and appends real-time viewport matrix data."""
        live_light_sys = self.light_sys
        live_scene_sys = self.scene_sys

        if not live_light_sys or not live_scene_sys:
            self.glob.env.logLine(1, "[Make Ligth, Preset Engine Error] Critical: True live viewport scene systems could not be resolved.")
            return

        # 1. LAUNCH THE METADATA WINDOW FOR MANUAL USER INPUT
        meta_dialog = SavePresetMetadataDialog(self)
        if meta_dialog.exec_() != QDialog.Accepted:
            self.glob.env.logLine(1, "[Make Light, Preset Engine] Save cycle aborted by user.")
            return
            
        user_meta = meta_dialog.get_metadata()
        preset_name = user_meta["name"]
        
        if not preset_name:
            QMessageBox.warning(self, "Invalid Name", "Preset profile name cannot be left blank.")
            return

        # create a clean name and save to user-presets
        clean_filename = self.glob.env.normalizeName(preset_name)
        target_file_path = os.path.join(self.user_presets_dir, f"{clean_filename}.json").replace("\\", "/")

        if os.path.isfile(target_file_path):
            confirm_overwrite = QMessageBox.question(
                self, "Preset Already Exists",
                f"A lighting profile named '{preset_name}' already exists.\n\nDo you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm_overwrite == QMessageBox.No:
                return

        try:
            # Calculate ambient lighting weight allocations, use endpoints defined in scene.py and light.py
            #
            amb_weight = live_light_sys.getAmbientLuminance() * 100.0
            amb_color_list = live_light_sys.getAmbientColor()
            clear_color_list = live_light_sys.getClearColor()
            floor_size_val = live_scene_sys.getFloorSizeFloat()
            floor_texture_str = live_scene_sys.getFloorTexture()

            compiled_lights_list = []

            for l_idx in range (live_light_sys.numLights()):
                l_color_list = live_light_sys.getLColor(l_idx)
                l_pos_list = live_light_sys.getLPos(l_idx)

                compiled_lights_list.append({
                    "id": l_idx,
                    "type": live_light_sys.getType(l_idx),
                    "luminance": live_light_sys.getLLuminance(l_idx),
                    "color": l_color_list,
                    "position": l_pos_list
                })

            preset_master_structure = {
                "preset_name": preset_name,
                "author": user_meta["author"],
                "notes": user_meta["notes"],
                "ambient_luminance": amb_weight,
                "ambient_color": amb_color_list,
                "clear_color": clear_color_list,
                "floor_texture": floor_texture_str, 
                "floor_size": floor_size_val,       
                "harsh_key_light": self.panel.harsh_light_toggle.isChecked(),
                "use_blinn_shading": self.panel.blinn_toggle.isChecked(),
                "use_toon_shading": self.panel.toon_toggle.isChecked(),
                "material_specular_focus": self.panel.specular_slider.value(),
                "lights": compiled_lights_list
            }

            with open(target_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(preset_master_structure, json_file, indent=4)

            self.scan_presets_folder()
            QMessageBox.information(self, "Preset Saved!", f"Successfully captured setup as '{preset_name}'!")

        except Exception as err:
            self.glob.env.logLine(1, f"[Make Light, Preset Engine Error] Automated scene serialization fault: {err}")

    def delete_selected_preset(self):
        """Erases files from local workspace path tracks safely."""
        current_item = self.panel.preset_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please highlight a lighting preset profile row from the list to delete.")
            return

        filename_key = current_item.data(Qt.UserRole)
        if not filename_key:
            return
        
        target_file_path = os.path.join(self.sys_presets_dir, filename_key).replace("\\", "/")

        confirm_box = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you absolutely sure you want to permanently delete the light preset file '{filename_key}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm_box == QMessageBox.Yes:
            try:
                if os.path.isfile(target_file_path):
                    os.remove(target_file_path)
                    self.glob.env.logLine(2, f"[Make Light, Preset Engine] Successfully removed file: {target_file_path}")
                    self.scan_presets_folder()
                    QMessageBox.information(self, "Deleted", "Successfully deleted preset file.")
                else:
                    QMessageBox.critical(self, "Error", "Could not delete: Preset file no longer exists at destination.")
            except Exception as delete_fault:
                self.glob.env.logLine(1, f"[Make Light, Preset Engine Error] System file removal operation collapsed: {delete_fault}")

    def execute_live_comparison_sweep(self):
        live_amb_lum = round(self.light_sys.getAmbientLuminance()  * 100.0, 1)
                    
        for row_idx in range(self.panel.preset_list.count()):
            list_item = self.panel.preset_list.item(row_idx)
            filename_key = list_item.data(Qt.UserRole)

            if not filename_key or filename_key not in self.scanned_presets:
                continue
                        
            f_data = self.scanned_presets[filename_key]
            raw_file_amb = f_data.get("ambient_luminance", 20.0)
                    
            if isinstance(raw_file_amb, (list, tuple, np.ndarray)):
                try:
                    flat_array = np.array(raw_file_amb).flatten()
                    raw_file_amb = flat_array[0] if flat_array.size > 0 else 20.0
                except Exception:
                    raw_file_amb = 20.0
                            
            try:
                file_amb_lum = round(float(raw_file_amb), 1)
            except (TypeError, ValueError):
                file_amb_lum = 20.0
                        
            if abs(live_amb_lum - file_amb_lum) < 0.5:
                theme_accent = QApplication.palette().color(QPalette.Highlight)
                theme_accent.setAlpha(45)
                list_item.setBackground(QBrush(theme_accent))
            else:
                list_item.setBackground(QBrush(QColor(0, 0, 0, 0)))


    def shutdown(self):
        self.glob.env.logLine(1, "[Light Presets shutdown ")
        if self.panel:
            self.deactivate_all_fx_overrides()
            self.panel.close()
            self.panel.deleteLater()

        self.stop_tracking_timer()

        if self.dock:
            self.main_window.removeDockWidget(self.dock)
            self.dock.close()
            self.dock.deleteLater()
        self.dock = None
        self.panel = None

    def initialize(self, docked=False):
        """
        the initialize function for this dock panel
        docked: if false, then standalone version is used
        """
        if self.pluginname in self.repo:
            # if loaded second time
            # Clean up old references just in case
            self.shutdown()

        # create the dock widget including UI
        #
        if docked:
            self.dock = QDockWidget("Community Lighting Presets Manager", self.main_window)
            self.dock.setObjectName("community_light_presets_dock_frame")
            self.dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
            self.panel = self.Panel(self)
            self.dock.setWidget(self.panel)
            if hasattr(self.main_window, "addDockWidget"):
                self.main_window.addDockWidget(Qt.RightDockWidgetArea, self.dock)
            else:
                self.dock.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            self.dock.show()
        else:
            self.panel = self.Panel(self)

        self.create_presets_directories()
        self.scan_presets_folder()

        # tracking timer
        #
        self.tracking_timer = QTimer(self)
        self.tracking_timer.timeout.connect(self.execute_live_comparison_sweep)
        self.tracking_timer.start(2000)

        QTimer.singleShot(100, self.establish_dock_signal_tracking_hooks)

        # now add plugin to repository
        #
        self.repo[self.pluginname] = self
        return True

def load_extension(app_reference, glob_reference=None):
    """
    MH2 COMPLIANCE HOOK: Spawns the panel container safely
    within the native dashboard interface framework.
    """
    glob_reference.env.logLine(1, "[Make Light] Initializing ...")

    pluginname = os.path.abspath(__file__)
    plugin = CommunityLightPresetPanel(app_reference, glob_reference, pluginname)
    return plugin.initialize(True)


def unload_extension(glob):
    pluginname = os.path.abspath(__file__)
    if pluginname in glob.pluginRepo:
        glob.pluginRepo[pluginname].shutdown()
        glob.pluginRepo.pop(pluginname)     # and delete from repo

