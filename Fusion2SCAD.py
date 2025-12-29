#Author: Fusion2SCAD
#Description: Export Fusion 360 parametric designs to OpenSCAD with BOSL2 support

import adsk.core
import adsk.fusion
import traceback
import os
import sys

# Add current directory to path for local imports
script_dir = os.path.dirname(os.path.realpath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import UI components
from ui import (
    ExportCommandCreatedHandler,
    COMMAND_ID,
    COMMAND_NAME,
    COMMAND_DESCRIPTION
)

# Global app references
app = adsk.core.Application.get()
ui = app.userInterface

# Keep track of event handlers to prevent garbage collection
handlers = []

# Keep track of UI elements for cleanup
toolbar_controls = []
command_definitions = []


def run(context):
    """Main entry point for the Fusion 360 add-in - creates toolbar button"""
    try:
        global toolbar_controls, command_definitions

        # Get the Design workspace
        design_workspace = ui.workspaces.itemById('FusionSolidEnvironment')

        if not design_workspace:
            ui.messageBox('Could not find Design workspace')
            return

        # Get the Tools tab
        tools_tab = design_workspace.toolbarTabs.itemById('ToolsTab')
        if not tools_tab:
            if design_workspace.toolbarTabs.count > 0:
                tools_tab = design_workspace.toolbarTabs.item(0)

        if not tools_tab:
            ui.messageBox('Could not find toolbar tab')
            return

        # Create a new panel or use existing one
        panel_id = 'Fusion2SCAD_Panel'
        panel = tools_tab.toolbarPanels.itemById(panel_id)

        if not panel:
            panel = tools_tab.toolbarPanels.add(panel_id, 'OpenSCAD Export')

        # Check if command already exists
        cmd_def = ui.commandDefinitions.itemById(COMMAND_ID)

        if cmd_def:
            cmd_def.deleteMe()

        # Create command definition with icon
        resources_folder = os.path.join(script_dir, 'resources')
        if not os.path.exists(resources_folder):
            resources_folder = ''

        cmd_def = ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID,
            COMMAND_NAME,
            COMMAND_DESCRIPTION,
            resources_folder
        )
        command_definitions.append(cmd_def)

        # Set tooltip
        cmd_def.tooltip = COMMAND_DESCRIPTION

        # Connect to command created event
        on_command_created = ExportCommandCreatedHandler()
        cmd_def.commandCreated.add(on_command_created)
        handlers.append(on_command_created)

        # Store execute handler if available
        execute_handler = on_command_created.get_execute_handler()
        if execute_handler:
            handlers.append(execute_handler)

        # Add button to panel
        button_control = panel.controls.itemById(COMMAND_ID)
        if not button_control:
            button_control = panel.controls.addCommand(cmd_def)
            button_control.isPromoted = True
            button_control.isPromotedByDefault = True
            toolbar_controls.append(button_control)

    except:
        if ui:
            ui.messageBox(f'Add-in initialization failed:\n{traceback.format_exc()}')


def stop(context):
    """Called when the add-in is stopped - cleanup UI elements"""
    try:
        global toolbar_controls, command_definitions, handlers

        # Remove toolbar controls
        for control in toolbar_controls:
            if control and control.isValid:
                control.deleteMe()
        toolbar_controls = []

        # Remove command definitions
        for cmd_def in command_definitions:
            if cmd_def and cmd_def.isValid:
                cmd_def.deleteMe()
        command_definitions = []

        # Clear handlers
        handlers = []

        # Try to remove the panel
        design_workspace = ui.workspaces.itemById('FusionSolidEnvironment')
        if design_workspace:
            tools_tab = design_workspace.toolbarTabs.itemById('ToolsTab')
            if tools_tab:
                panel = tools_tab.toolbarPanels.itemById('Fusion2SCAD_Panel')
                if panel and panel.isValid:
                    panel.deleteMe()

    except:
        if ui:
            ui.messageBox(f'Add-in cleanup failed:\n{traceback.format_exc()}')
