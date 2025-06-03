import numpy as np

from qtpy import QtWidgets, QtCore

from pymodaq_utils.utils import ThreadCommand, recursive_find_files_extension
from pymodaq.utils.data import DataFromPlugins, Axis, DataToExport
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.parameter import Parameter
from pymodaq.utils.parameter import utils as putils
from pymodaq.utils.enums import BaseEnum
from pymodaq.utils.gui_utils import select_file, ListPicker
from pymodaq_gui.parameter.utils import set_param_from_param

from harvesters.core import Harvester, ImageAcquirer, Callback
from harvesters.util.pfnc import mono_location_formats, \
    rgb_formats, bgr_formats, \
    rgba_formats, bgra_formats

try:
    cti_paths = recursive_find_files_extension(r'C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64', 'cti')
except:
    try:
        cti_paths = recursive_find_files_extension(r'C:\Program Files\Teledyne\Spinnaker\cti64\vs2015', 'cti')
    except:
        cti_paths = []


class EInterfaceType(BaseEnum):
    """
    typedef for interface type
    """
    intfIValue = 0       #: IValue interface
    intfIBase = 1        #: IBase interface
    intfIInteger = 2     #: IInteger interface
    intfIBoolean = 3     #: IBoolean interface
    intfICommand = 4     #: ICommand interface
    intfIFloat = 5       #: IFloat interface
    intfIString = 6      #: IString interface
    intfIRegister = 7    #: IRegister interface
    intfICategory = 8    #: ICategory interface
    intfIEnumeration = 9  #: IEnumeration interface
    intfIEnumEntry = 10   #: IEnumEntry interface
    intfIPort = 11  #: IPort interface


harv = Harvester()


for path in cti_paths:
    harv.add_cti_file(path)
    harv.update_device_info_list()
devices = harv.device_info_list
devices_names = [device.model for device in devices]


class DAQ_2DViewer_GenICam(DAQ_Viewer_base):
    """ Instrument plugin class for a 2D viewer.
    
    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Viewer module through inheritance via
    DAQ_Viewer_base. It makes a bridge between the DAQ_Viewer module and the Python wrapper of a particular instrument.

       Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.
         
    """
    params = comon_parameters + \
             [
                 {'title': 'Cam. names:', 'name': 'cam_name', 'type': 'list',
                  'limits': devices_names},
                 {'title': 'Update features:', 'name': 'update_features', 'type': 'bool_push',
                  'value': False},
                 {'title': 'Cam. Prop.:', 'name': 'cam_settings', 'type': 'group', 'children': []},
              ]

    def ini_attributes(self):
        self.controller: ImageAcquirer = None

        self.x_axis: Axis = None
        self.y_axis: Axis = None

        self.width = None
        self.width_max = None
        self.height = None
        self.height_max = None
        self.data = None

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() in putils.iter_children(self.settings.child('cam_settings'), []):

            self.stop()
            while self.controller.is_acquiring():
                self.stop()
                QtWidgets.QApplication.processEvents()

            feature = self.controller.remote_device.node_map.get_node(param.name())
            interface_type = feature.node.principal_interface_type
            if interface_type == EInterfaceType.intfIInteger.value:
                val = int((param.value() // param.opts['step']) * param.opts['step'])
            else:
                val = param.value()
            feature.value = val  # set the desired value
            param.setValue(feature.value)  # retrieve the actually set one

            if param.name() in ['Height', 'Width', 'OffsetX', 'OffsetY']:
                    self.width = self.controller.remote_device.node_map.get_node('Width').value
                    self.height = self.controller.remote_device.node_map.get_node('Height').value
                    self.get_yaxis()
                    self.get_xaxis()
                    self.data = np.zeros((self.height, self.width))

        elif param.name() == "update_features":
            if param.value():
                self.get_features()
                self.settings.child("update_features").setValue(False)
        ##deprecated
        # if param.name() in putils.iter_children(self.settings.child('ROIselect'), []):
        #
        #     while self.controller.is_acquiring_images:
        #         QtCore.QThread.msleep(50)
        #         self.stop()
        #         QtWidgets.QApplication.processEvents()
        #
        #     self.set_ROI()

    def set_ROI(self):  #todo this should be rewritten because ROIselect is no more part of
        # common settings,
        # see: https://github.com/PyMoDAQ/pymodaq_plugins_mockexamples/blob/main/src/pymodaq_plugins_mockexamples/daq_viewer_plugins/plugins_2D/daq_2Dviewer_RoiStuff.py
        params = putils.iter_children_params(self.settings.child('cam_settings'), [])
        param_names = [param.name() for param in params]

        if self.settings.child('ROIselect', 'use_ROI').value():
            #one starts by settings width and height so that offset could be set accordingly
            param = self.settings.child('ROIselect','width')
            param_to_set = params[param_names.index('Width')]
            step = param_to_set.opts['step']
            val = int((param.value() // step) * step)
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('Width').value = val

            param = self.settings.child('ROIselect', 'height')
            param_to_set = params[param_names.index('Height')]
            step = param_to_set.opts['step']
            val = int((param.value() // step) * step)
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('Height').value = val


            param = self.settings.child('ROIselect', 'x0')
            param_to_set = params[param_names.index('OffsetX')]
            step = param_to_set.opts['step']
            val = int((param.value() // step) * step)
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('OffsetX').value = val

            param = self.settings.child('ROIselect', 'y0')
            param_to_set = params[param_names.index('OffsetY')]
            step = param_to_set.opts['step']
            val = int((param.value() // step) * step)
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('OffsetY').value = val

        else:
            # one starts by settings offsets so that width and height could be set accordingly
            param_to_set = params[param_names.index('OffsetX')]
            val = 0
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('OffsetX').value = val

            param_to_set = params[param_names.index('OffsetY')]
            val = 0
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('OffsetY').value = val

            param_to_set = params[param_names.index('Width')]
            val = self.width_max
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('Width').value = val


            param_to_set = params[param_names.index('Height')]
            val = self.height_max
            param_to_set.setValue(val)
            self.controller.remote_device.node_map.get_node('Height').value = val

    def get_features(self):
        features = self.controller.remote_device.node_map.Root.features

        if self.settings.child('cam_settings').hasChildren():
            newsettings = Parameter.create(name='cam_settings', type='group', children=self.populate_settings(features))
            set_param_from_param(self.settings.child('cam_settings'), newsettings)

        else:
            self.settings.child('cam_settings').addChildren(self.populate_settings(features))


    def populate_settings(self, features, param_list: list = None):
        if param_list is None:
            param_list = []
        for feature in features:
            try:
                if feature.node.visibility == 0:  # parameters for "beginners"
                    interface_type = feature.node.principal_interface_type
                    item = {}
                    if interface_type == EInterfaceType.intfIBoolean.value:
                        item.update({'type': 'bool',
                                     'value': True if feature.value.lower() == 'true' else False,
                                     'readonly': feature.get_access_mode() in [0, 1, 3],
                                     'enabled': not (feature.get_access_mode() in [0, 1, 3])})
                    elif interface_type == EInterfaceType.intfIFloat.value:
                        item.update({'type': 'float', 'value': feature.value,
                                     'readonly': feature.get_access_mode() in [0, 1, 3],
                                     'enabled': not (feature.get_access_mode() in [0, 1, 3]),
                                     'min': feature.min,
                                     'max': feature.max})
                    elif interface_type == EInterfaceType.intfIInteger.value:
                        item.update({'type': 'int', 'value': feature.value,
                                     'step': feature.inc,
                                     'readonly': feature.get_access_mode() in [0, 1, 3],
                                     'enabled': not (feature.get_access_mode() in [0, 1, 3]),
                                     'min': feature.min,
                                     'max': feature.max})
                        # print(feature.node.name)
                    elif interface_type == EInterfaceType.intfIString.value:
                        item.update({'type': 'str', 'value': feature.value,
                                     'readonly': feature.get_access_mode() in [0, 1, 3],
                                     'enabled': not (feature.get_access_mode() in [0, 1, 3])
                                     })

                    elif interface_type == EInterfaceType.intfIEnumeration.value:
                        limits_dict = {}
                        for f in feature.entries:
                            limits_dict[f.node.display_name] = f.symbolic
                        item.update({'type': 'list', 'value': feature.value,
                                     'limits': limits_dict,
                                     'readonly': feature.get_access_mode() in [0, 1, 3],
                                     'enabled': not (feature.get_access_mode() in [0, 1, 3])
                                     })

                    elif interface_type == EInterfaceType.intfICategory.value:
                        new_list = []
                        item.update({'type': 'group',
                                     'children': self.populate_settings(feature.node.children,
                                                                        new_list)})
                    else:
                        continue
                    item.update({'title': feature.node.display_name, 'name': feature.node.name,
                                 'tooltip': feature.node.description})
                    param_list.append(item)
            except:
                pass

        return param_list

    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.ini_detector_init(old_controller=controller,
                               new_controller=None)

        if self.settings.child('controller_status').value() == "Master":
            if cti_paths == []:
                file = select_file(start_path=r'C:\Program Files', save=False, ext='cti')
                if file != '':
                    cti_paths.append(str(file))
                for path in cti_paths:
                    harv.add_cti_file(path)
                    harv.update_device_info_list()
                devices = harv.device_info_list
                devices_names = [device.model for device in devices]
                # device = QtWidgets.QInputDialog.getItem(None, 'Pick an item', 'List of discovered cameras:', devices_names, editable = False)

                self.settings.child('cam_name').setLimits(devices_names)
                self.settings.child('cam_name').setValue(devices_names[0])
                QtWidgets.QApplication.processEvents()

            self.controller = harv.create({'model': self.settings.child('cam_name').value()})
            # self.controller.num_buffers = 2
            self.controller.remote_device.node_map.get_node('OffsetX').value = 0
            self.controller.remote_device.node_map.get_node('OffsetY').value = 0
            self.controller.remote_device.node_map.get_node(
                'Width').value = self.controller.remote_device.node_map.get_node('Width').max
            self.controller.remote_device.node_map.get_node(
                'Height').value = self.controller.remote_device.node_map.get_node('Height').max
            self.get_features()

        on_new_buffer_callback =  CallbackOnNewBuffer()
        self.callback_thread = QtCore.QThread()
        on_new_buffer_callback.moveToThread(self.callback_thread)
        on_new_buffer_callback.frames_available.connect(self.emit_data)

        self.controller.add_callback(
             ImageAcquirer.Events.NEW_BUFFER_AVAILABLE,
             on_new_buffer_callback
        )

        self.x_axis = self.get_xaxis()
        self.y_axis = self.get_yaxis()
        self.width_max = self.controller.remote_device.node_map.get_node('Width').max
        self.width = self.controller.remote_device.node_map.get_node('Width').value
        self.height_max = self.controller.remote_device.node_map.get_node('Height').max
        self.height = self.controller.remote_device.node_map.get_node('Height').value
        self.data = np.zeros((self.height, self.width))
        # initialize viewers with the future type of data
        self.dte_signal_temp.emit(
            DataToExport('myplugin',
                         data=[
                             DataFromPlugins(name='GenICam', data=[self.data], dim='Data2D',
                                             axes=[self.x_axis, self.y_axis])]))


        info = "Whatever info you want to log"
        initialized = True
        return info, initialized

    def get_xaxis(self) -> Axis:
        """

        """
        Nx = self.controller.remote_device.node_map.get_node('Width').value
        self.x_axis = Axis('xaxis', units='pxls', data=np.linspace(0, Nx-1, Nx, dtype=np.int32),
                           index=1)
        return self.x_axis

    def get_yaxis(self):
        """

        """
        Ny = self.controller.remote_device.node_map.get_node('Height').value
        self.y_axis = Axis('yaxis', units='pxls', data=np.linspace(0, Ny-1, Ny, dtype=np.int32),
                           index=0)
        return self.y_axis

    def close(self):
        """Terminate the communication protocol"""
        self.stop()
        self.controller.destroy()
        harv.reset()

    def emit_data(self):

        with self.controller.fetch() as buffer:
            payload = buffer.payload
            component = payload.components[0]
            width = component.width
            height = component.height
            data_format = component.data_format

            # if self.settings.child('ROIselect', 'use_ROI').value():
            #     offsetx = self.controller.remote_device.node_map.get_node('OffsetX').value
            #     offsety = self.controller.remote_device.node_map.get_node('OffsetY').value
            # else:
            #     offsetx = 0
            #     offsety = 0
            offsetx = 0
            offsety = 0

            if data_format in mono_location_formats:
                data_tmp = component.data.reshape(height, width)
                self.data[offsety:offsety + height, offsetx:offsetx + width] = data_tmp
                self.dte_signal.emit(
                    DataToExport('myplugin',
                                 data=[
                                     DataFromPlugins(name='GenICam', data=[self.data],
                                                     dim='Data2D',
                                                     axes=[self.x_axis, self.y_axis])]))
            else:
                # The image requires you to reshape it to draw it on the canvas:
                if data_format in rgb_formats or \
                        data_format in rgba_formats or \
                        data_format in bgr_formats or \
                        data_format in bgra_formats:
                    #
                    content = component.data.reshape(height, width,
                                                     int(component.num_components_per_pixel)
                                                     # Set of R, G, B, and Alpha
                                                     )
                    #
                    if data_format in bgr_formats:
                        # Swap every R and B:
                        content = content[:, :, ::-1]
                self.data_grabed_signal.emit(
                    DataToExport('myplugin',
                                 data=[
                                     DataFromPlugins(name='GenICam',
                                                     data=[
                                                         self.data[:, :, ind] for ind in
                                                         range(min(3, component.num_components_per_pixel))],
                                                     dim='Data2D',
                                                     axes=[self.x_axis, self.y_axis])]))



    def grab_data(self, Naverage=1, **kwargs):
        """Start a grab from the detector

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging (if hardware averaging is possible, self.hardware_averaging should be set to
            True in class preamble and you should code this implementation)
        kwargs: dict
            others optionals arguments
        """
        if 'live' in kwargs:
            self.live = kwargs['live']

        if not self.controller.is_acquiring():
            self.controller.start(run_as_thread=True)  # set to True in order to catch `NEW_BUFFER_AVAILABLE` event


    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        self.controller.stop()


class CallbackOnNewBuffer(QtCore.QObject, Callback):
    # Callback class to handle new buffer arrivals
    # Follows instructions from https://github.com/genicam/harvesters/wiki/FAQ
    frames_available = QtCore.Signal()

    def __init__(self, wait_time=10):
        super().__init__()
        self.wait_time = wait_time

    def emit(self, context):
        self.frames_available.emit()
        QtCore.QThread.msleep(self.wait_time)


if __name__ == '__main__':
    main(__file__, init=True)
