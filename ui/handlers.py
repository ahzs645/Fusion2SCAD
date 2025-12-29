#Author: Fusion2SCAD
#Description: Fusion 360 UI event handlers for OpenSCAD export

import adsk.core
import adsk.fusion
import traceback
import os
import json
import datetime

from exporter import SCADExporter

# Global app references
app = adsk.core.Application.get()
ui = app.userInterface

# Command identifiers
COMMAND_ID = 'Fusion2SCAD_Export'
COMMAND_NAME = 'Export to OpenSCAD'
COMMAND_DESCRIPTION = 'Export parametric design to OpenSCAD with BOSL2 support'


class ExportCommandExecuteHandler(adsk.core.CommandEventHandler):
    """Handler for when the export command is executed"""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(app.activeProduct)

            if not design:
                ui.messageBox('No active Fusion 360 design found.\nPlease open a design first.')
                return

            # Create file dialog
            file_dialog = ui.createFileDialog()
            file_dialog.isMultiSelectEnabled = False
            file_dialog.title = "Export to OpenSCAD (BOSL2)"
            file_dialog.filter = "OpenSCAD files (*.scad)"

            # Generate timestamped filename
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d at %I.%M.%S %p")
            file_dialog.initialFilename = f"{design.rootComponent.name} {timestamp}.scad"

            # Default to Desktop
            file_dialog.initialDirectory = os.path.expanduser("~/Desktop")

            dialog_result = file_dialog.showSave()

            if dialog_result != adsk.core.DialogResults.DialogOK:
                return

            filepath = file_dialog.filename

            # Export the design
            exporter = SCADExporter(design)
            scad_content = exporter.export()

            # Write SCAD file
            with open(filepath, 'w') as f:
                f.write(scad_content)

            # Also export debug JSON
            debug_filepath = filepath.replace('.scad', '_debug.json')
            debug_data = exporter.export_debug_json()
            with open(debug_filepath, 'w') as f:
                json.dump(debug_data, f, indent=2)

            # Show success message with summary
            param_count = len(exporter.parameters)
            feature_count = len(debug_data['features'])
            ui.messageBox(
                f'Export successful!\n\n'
                f'SCAD File: {filepath}\n'
                f'Debug JSON: {debug_filepath}\n\n'
                f'Parameters exported: {param_count}\n'
                f'Features exported: {feature_count}\n\n'
                f'Note: Make sure BOSL2 is installed in your OpenSCAD libraries folder.'
            )

        except:
            if ui:
                ui.messageBox(f'Export failed:\n{traceback.format_exc()}')


class ExportCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for when the command is created"""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command

            # Connect to the execute event
            on_execute = ExportCommandExecuteHandler()
            cmd.execute.add(on_execute)
            # Return handler to be stored by caller
            self._execute_handler = on_execute

        except:
            if ui:
                ui.messageBox(f'Command created failed:\n{traceback.format_exc()}')

    def get_execute_handler(self):
        """Return the execute handler for storage"""
        return getattr(self, '_execute_handler', None)
