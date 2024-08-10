import napari
from qtpy.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QComboBox, QLabel, 
                            QLineEdit, QFormLayout, QScrollArea)
from qtpy.QtCore import Qt
import requests
import copick

class CellCanvasWidget(QWidget):
    def __init__(self, copick_config_path="/Users/kharrington/Data/copick/cellcanvas_server/local_sshOverlay_localStatic.json", hostname="localhost", port=8082, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CellCanvas Widget")
        self.hostname = hostname
        self.port = port
        self.copick_config_path = copick_config_path
        self.layout = QVBoxLayout(self)
        
        # Load Copick project
        self.root = copick.from_file(self.copick_config_path)
        
        # Run selection dropdown
        self.run_dropdown = QComboBox(self)
        self.layout.addWidget(QLabel("Select Run:"))
        self.layout.addWidget(self.run_dropdown)
        self.populate_run_dropdown()
        
        # Solution selection dropdown
        self.solution_dropdown = QComboBox(self)
        self.layout.addWidget(QLabel("Select Solution:"))
        self.layout.addWidget(self.solution_dropdown)
        self.populate_solution_dropdown()
        
        # Scroll area for solution arguments
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QFormLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)
        
        # Run solution button
        self.run_button = QPushButton("Run Solution", self)
        self.run_button.clicked.connect(self.run_solution)
        self.layout.addWidget(self.run_button)
        
        self.setLayout(self.layout)
        self.run_dropdown.currentIndexChanged.connect(self.update_solution_args)
        self.solution_dropdown.currentIndexChanged.connect(self.update_solution_args)
        self.update_solution_args()

    def populate_run_dropdown(self):
        self.run_dropdown.clear()
        for run in self.root.runs:
            self.run_dropdown.addItem(run.meta.name)

    def populate_solution_dropdown(self):
        self.solution_dropdown.clear()
        try:
            response = requests.get(f"http://{self.hostname}:{self.port}/index")
            if response.status_code == 200:
                index = response.json().get('index', {})
                for solution_id, solution_info in index.items():
                    self.solution_dropdown.addItem(f"{solution_info['catalog']}:{solution_info['group']}:{solution_info['name']}:{solution_info['version']}")
        except Exception as e:
            print(f"Error fetching solutions: {e}")

    def update_solution_args(self):
        # Clear existing widgets
        for i in reversed(range(self.scroll_layout.count())): 
            widget = self.scroll_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()  # Ensures the widget is fully cleaned up
                self.scroll_layout.removeWidget(widget)
        
        selected_run = self.run_dropdown.currentText()
        selected_solution = self.solution_dropdown.currentText()
        
        if not selected_solution:
            return

        catalog, group, name, version = selected_solution.split(":")

        # Define the conditions for freeform parameters
        freeform_conditions = {
            "cellcanvas": {
                "generate-pixel-embedding": ["embedding_name"],
                "generate-tomogram": ["run_name"],
                "generate-skimage-features": ["feature_type"],
            }
        }

        try:
            response = requests.get(f"http://{self.hostname}:{self.port}/info/{catalog}/{group}/{name}/{version}")
            if response.status_code == 200:
                solution_info = response.json().get('info', {})
                args = solution_info.get('args', [])
                
                for arg in args:
                    arg_name = arg.get('name')
                    arg_type = arg.get('type')
                    default_value = arg.get('default', '')
                    
                    label = QLabel(arg_name)
                    
                    # Check if the parameter should be freeform or dropdown
                    if arg_name == 'copick_config_path':
                        field = QLineEdit(str(self.copick_config_path))
                    elif catalog in freeform_conditions and name in freeform_conditions[catalog] and arg_name in freeform_conditions[catalog][name]:
                        field = QLineEdit(str(default_value))
                    else:
                        if arg_name == 'run_name':
                            field = QComboBox()
                            for run in self.root.runs:
                                field.addItem(run.meta.name)
                            field.setCurrentText(selected_run)
                        elif arg_name == 'voxel_spacing':
                            field = QComboBox()
                            run = self.root.get_run(selected_run)
                            for voxel_spacing in run.voxel_spacings:
                                field.addItem(str(voxel_spacing.meta.voxel_size))
                        elif arg_name == 'tomo_type':
                            field = QComboBox()
                            run = self.root.get_run(selected_run)
                            for tomogram in run.voxel_spacings[0].tomograms:
                                field.addItem(tomogram.meta.tomo_type)
                        elif arg_name in ['embedding_name', 'feature_type']:
                            field = QComboBox()
                            run = self.root.get_run(selected_run)
                            for voxel_spacing in run.voxel_spacings:
                                for tomogram in voxel_spacing.tomograms:
                                    for feature in tomogram.features:
                                        field.addItem(feature.meta.name)
                        else:
                            field = QLineEdit(str(default_value))
                    
                    self.scroll_layout.addRow(label, field)

                # Ensure the widgets are updated to avoid event filter issues
                self.scroll_content.update()
        except Exception as e:
            print(f"Error updating solution args: {e}")

    def run_solution(self):
        selected_solution = self.solution_dropdown.currentText()
        if not selected_solution:
            return

        catalog, group, name, version = selected_solution.split(":")
        solution_args = {}
        
        for i in range(self.scroll_layout.rowCount()):
            label_item = self.scroll_layout.itemAt(i * 2)
            field_item = self.scroll_layout.itemAt(i * 2 + 1)
            if label_item and field_item:
                label = label_item.widget()
                field = field_item.widget()
                if isinstance(field, QComboBox):
                    solution_args[label.text()] = field.currentText()
                else:
                    solution_args[label.text()] = field.text()
        
        try:
            response = requests.post(f"http://{self.hostname}:{self.port}/run/{catalog}/{group}/{name}/{version}", 
                                     json={"args": solution_args})
            if response.status_code == 200:
                result = response.json()
                print(f"Execution result: {result}")
            else:
                print(f"Failed to execute solution. Status code: {response.status_code}")
                print(f"Response content: {response.text}")
        except Exception as e:
            print(f"Error occurred: {e}")

def main():
    viewer = napari.Viewer()
    widget = CellCanvasWidget()
    viewer.window.add_dock_widget(widget, area='right')
    napari.run()

if __name__ == "__main__":
    main()
