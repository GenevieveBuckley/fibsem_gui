import os
import os.path as p
import time

import skimage.util
import numpy as np
import scipy.ndimage as ndi
import skimage
import skimage.color
import skimage.io
import skimage.transform

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import \
    FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import \
    NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from skimage.transform import AffineTransform
from piescope_gui._version import __version__


def open_correlation_window(main_gui, fluorescence_image, fibsem_image, output_path):
    """Opens a new window to perform correlation

    Parameters
    ----------
    main_gui : PyQt5 Window

    fluorescence_image : numpy.array with shape: (rows, columns) or path
        to numpy.array with shape: (rows, columns)

    fibsem_image : expecting Adorned Image or path to Adorned image

    output_path : path to save location
    """
    global img1
    global img2
    global img1_path
    global img2_path
    global gui
    global output
    global fluorescence_original

    gui = main_gui
    fluorescence_original = fluorescence_image

    if type(fluorescence_image) == str:
        print("Image 1 given as path")
        fluorescence_image_rgb = skimage.color.gray2rgb(plt.imread(fluorescence_image))
    else:
        print("Image 1 given as array")
        fluorescence_image_rgb = np.copy(fluorescence_image)

    if type(fibsem_image) == str:
        print("Image 2 given as path")
        fibsem_image = skimage.color.gray2rgb(plt.imread(fibsem_image))
    else:
        fibsem_data = np.copy(fibsem_image.data)
        print("Image 2 given as array")
        fibsem_image = skimage.color.gray2rgb(fibsem_data)

        fluorescence_image_rgb = skimage.transform.resize(fluorescence_image_rgb, fibsem_image.shape)

    img1 = fluorescence_image_rgb
    img2 = fibsem_image
    output = output_path

    window = _CorrelationWindow(parent=gui)
    return window


def correlate_images(fluorescence_image_rgb, fibsem_image, output, matched_points_dict):
    """Correlates two images using points chosen by the user

    Parameters
    ----------
    fluorescence_image_rgb :
        umpy array with shape (cols, rows, channels)
    fibsem_image : AdornedImage.
        Expecting .data attribute of shape (cols, rows, channels)
    output : str
        Path to save location

    matched_points_dict : dict
    Dictionary of points selected in the correlation window
    """
    if matched_points_dict == []:
        print('No control points selected, exiting.')
        return

    src, dst = point_coords(matched_points_dict)
    transformation = calculate_transform(src, dst)
    fluorescence_image_aligned = apply_transform(fluorescence_image_rgb, transformation)
    result = overlay_images(fluorescence_image_aligned, fibsem_image.data)
    result = skimage.util.img_as_ubyte(result)

    # TODO: the only imports here should be numpy arrays, not AdornedImagE
    # TODO: get rid of this, saving should happen outside the function
    # overlay_adorned_image = AdornedImage(result)
    # overlay_adorned_image.metadata = gui.fibsem_image.metadata
    # save_text(output, transformation, matched_points_dict)
    # plt.imsave(output, result)
    # overlay_adorned_image.save(output)

    return result#, overlay_adorned_image, fluorescence_image_rgb, fluorescence_original


class _CorrelationWindow(QMainWindow):
    """Main correlation window"""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.create_window()
        self.create_conn()

        self.wp.canvas.fig.subplots_adjust(
            left=0.01, bottom=0.01, right=0.99, top=0.99)

        q1 = QTimer(self)
        q1.setSingleShot(False)
        q1.timeout.connect(self.updateGUI)
        q1.start(10000)

    def create_window(self):
        self.setWindowTitle("Control Point Selection Tool")

        widget = QWidget(self)

        self.setCentralWidget(widget)

        hlay = QHBoxLayout(widget)
        vlay = QVBoxLayout()
        vlay2 = QVBoxLayout()
        vlay2.setSpacing(20)
        hlay_buttons = QHBoxLayout()

        hlay.addLayout(vlay)
        hlay.addLayout(vlay2)

        self.wp = _WidgetPlot(self)
        vlay.addWidget(self.wp)

        self.help = QTextEdit()
        self.help.setReadOnly(True)
        self.help.setMaximumWidth(400)
        self.help.setMinimumHeight(540)

        help_header = '<!DOCTYPE html><html lang="de" ' \
                      'id="main"><head><meta charset="UTF-8"><title>' \
                      'Description of cpselect for Python</title><style>td,' \
                      'th{font-size:14px;}p{font-size: 14px;}</style></head>'
        help_body = '<body><h1>Description of cpselect for Python&emsp;' \
                    '</h1><h2>Navigation Toolbar</h2><img src="{}" ' \
                    'alt="navbuttons"><br/><table cellspacing="20px"><tr>' \
                    '<th valign="middle" height="20px">Tool</th><th valign=' \
                    '"middle" height="20px">how to use</th></tr><tr><td>' \
                    '<img src="{}" alt="homebutton"></td>' \
                    '<td valign="middle">For all Images, reset ' \
                    'to the original view.</td></tr><tr><td>' \
                    '<img src="{}" alt="backwardforwardbutton">' \
                    '</td><td valign="middle">Go back to the last ' \
                    'or forward to the next view.</td></tr><tr><td>' \
                    '<img src="{}" alt="panzoombutton"></td>' \
                    '<td valign="middle">Activate the pan/zoom tool. ' \
                    'Pan with left mouse button, zoom with right</td></tr>' \
                    '<tr><td><img src="{}" alt="backwardforwardbutton">' \
                    '</td><td valign="middle">Zoom with drawing a rectangle' \
                    '</td></tr></table><h2>Pick Mode</h2><p>' \
                    'Change into pick mode to pick up your control points. ' \
                    'You have to pick the control points in both images ' \
                    'before you can start to pick the next point.</p><p>' \
                    'Press the red button below to start pick mode.</p><h2>' \
                    'Control Point list</h2><p>Below in the table, all ' \
                    'your control points are listed. You can delete one or ' \
                    'more selected control points with the <b>delete</b> ' \
                    'button.</p><h2>Return</h2><p>If you are finished, ' \
                    'please press the <b>return</b> button below. You will' \
                    ' come back to wherever you have been.</p></body></html>'
        help_html = help_header + help_body.format(
            os.path.join(os.path.dirname(__file__), "img/navbuttons.PNG"),
            os.path.join(os.path.dirname(__file__), "img/homebutton.png"),
            os.path.join(os.path.dirname(__file__),
                         "img/backforwardbutton.png"),
            os.path.join(os.path.dirname(__file__), "img/panzoombutton.png"),
            os.path.join(os.path.dirname(__file__), "img/zoomboxbutton.png"),
        )
        self.help.insertHtml(help_html)
        self.cpTabelModel = QStandardItemModel(self)
        self.cpTable = QTableView(self)
        self.cpTable.setModel(self.cpTabelModel)
        self.cpTable.setMaximumWidth(400)

        self.delButton = QPushButton("Delete selected Control Point")
        self.delButton.setStyleSheet("font-size: 16px")

        self.pickButton = QPushButton("pick mode")
        self.pickButton.setFixedHeight(60)
        self.pickButton.setStyleSheet("color: red; font-size: 16px;")

        self.exitButton = QPushButton("Return")
        self.exitButton.setFixedHeight(60)
        self.exitButton.setStyleSheet("font-size: 16px;")

        vlay2.addWidget(self.help)
        vlay2.addWidget(self.cpTable)
        vlay2.addWidget(self.delButton)

        vlay2.addLayout(hlay_buttons)
        hlay_buttons.addWidget(self.pickButton)
        hlay_buttons.addWidget(self.exitButton)

        self.updateCPtable()
        self.statusBar().showMessage("Ready")

    def create_conn(self):
        self.pickButton.clicked.connect(self.pickmodechange)
        self.delButton.clicked.connect(self.delCP)

    def menu_quit(self):
        matched_points_dict = self.get_dictlist()
        # TODO: correlation fix
        # result, overlay_adorned_image, fluorescence_image_rgb, fluorescence_original = correlate_images(img1, img2, output, matched_points_dict)
        result = correlate_images(img1, img2, output, matched_points_dict)
        self.close()
        # return result, overlay_adorned_image, fluorescence_image_rgb, fluorescence_original, output, matched_points_dict
        return result

    def get_dictlist(self):
        dictlist = []
        for cp in self.wp.canvas.CPlist:
            dictlist.append(cp.getdict)
        return dictlist

    def pickmodechange(self):

        if self.wp.canvas.toolbar._active in ["", None]:
            if self.wp.canvas.pickmode == True:
                self.wp.canvas.pickMode_changed = True
                self.wp.canvas.pickmode = False
                self.statusBar().showMessage("Pick Mode deactivate.")
                self.wp.canvas.cursorGUI = "arrow"
                self.wp.canvas.cursorChanged = True
            else:
                self.wp.canvas.pickMode_changed = True
                self.wp.canvas.pickmode = True
                self.wp.canvas.toolbar._active = ""
                self.statusBar().showMessage(
                    "Pick Mode activate. Select Control Points."
                )
        else:
            self.statusBar().showMessage(
                f"Please, first deactivate the selected navigation tool"
                f"{self.wp.canvas.toolbar._active}",
                3000,
            )

    def delCP(self):
        rows = self.cpTable.selectionModel().selectedRows()
        for row in rows:
            try:
                idp = int(row.data())
                for cp in self.wp.canvas.CPlist:
                    if cp.idp == idp:
                        index = self.wp.canvas.CPlist.index(cp)
                        self.wp.canvas.CPlist.pop(index)
            except Exception as e:
                print("Error occured: '{}'".format(e))
                pass

        self.wp.canvas.updateCanvas()
        self.wp.canvas.cpChanged = True

    def updateGUI(self):
        if self.wp.canvas.toolbar._active not in ["", None]:
            self.wp.canvas.pickmode = False
            self.wp.canvas.pickMode_changed = True

        if self.wp.canvas.pickMode_changed:
            if not self.wp.canvas.pickmode:
                self.pickButton.setStyleSheet("color: red; font-size: 20px;")
            elif self.wp.canvas.pickmode:
                self.pickButton.setStyleSheet("color: green; font-size: 20px;")
            self.wp.canvas.pickMode_changed = False

        if self.wp.canvas.cursorChanged:
            if self.wp.canvas.cursorGUI == "cross":
                QApplication.setOverrideCursor(QCursor(Qt.CrossCursor))
            elif self.wp.canvas.cursorGUI == "arrow":
                QApplication.restoreOverrideCursor()
            self.wp.canvas.cursorChanged = False

        if self.wp.canvas.cpChanged:
            self.updateCPtable()

    def updateCPtable(self):
        self.wp.canvas.cpChanged = False
        self.cpTable.clearSelection()
        self.cpTabelModel.clear()
        self.cpTabelModel.setHorizontalHeaderLabels(
        ["Point Number", "x (Img 1)", "y (Img 1)", "x (Img 2)", "y (Img 2)"]
        )

        for cp in self.wp.canvas.CPlist:
            idp, x1, y1, x2, y2 = cp.coordText

            c1 = QStandardItem(idp)
            c2 = QStandardItem(x1)
            c3 = QStandardItem(y1)
            c4 = QStandardItem(x2)
            c5 = QStandardItem(y2)

            row = [c1, c2, c3, c4, c5]

            for c in row:
                c.setTextAlignment(Qt.AlignCenter)
                c.setFlags(Qt.ItemIsEditable)
                c.setFlags(Qt.ItemIsSelectable)

            self.cpTabelModel.appendRow(row)

        self.cpTable.resizeColumnsToContents()


class _WidgetPlot(QWidget):
    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        self.setLayout(QVBoxLayout())
        self.canvas = _PlotCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.layout().addWidget(self.toolbar)
        self.layout().addWidget(self.canvas)


class _PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure()
        FigureCanvas.__init__(self, self.fig)

        self.setParent(parent)
        FigureCanvas.setSizePolicy(
            self, QSizePolicy.Expanding, QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)
        self.plot()
        self.createConn()

        self.figureActive = False
        self.axesActive = None
        self.CPactive = None
        self.pickmode = False
        self.pickMode_changed = True
        self.cpChanged = False
        self.cursorGUI = "arrow"
        self.cursorChanged = False
        self.CPlist = []
        self.lastIDP = 0

    def plot(self):
        gs0 = self.fig.add_gridspec(1, 2)

        self.ax11 = self.fig.add_subplot(
            gs0[0], xticks=[], yticks=[], title="Image 1: Select Points")
        self.ax12 = self.fig.add_subplot(
            gs0[1], xticks=[], yticks=[], title="Image 2: Select Points")

        self.ax11.imshow(img1)
        self.ax12.imshow(img2)

    def updateCanvas(self, event=None):
        ax11_xlim = self.ax11.get_xlim()
        ax11_xvis = ax11_xlim[1] - ax11_xlim[0]
        ax12_xlim = self.ax12.get_xlim()
        ax12_xvis = ax12_xlim[1] - ax12_xlim[0]

        while len(self.ax11.patches) > 0:
            [p.remove() for p in self.ax11.patches]
        while len(self.ax12.patches) > 0:
            [p.remove() for p in self.ax12.patches]
        while len(self.ax11.texts) > 0:
            [t.remove() for t in self.ax11.texts]
        while len(self.ax12.texts) > 0:
            [t.remove() for t in self.ax12.texts]

        ax11_units = ax11_xvis * 0.003
        ax12_units = ax12_xvis * 0.003

        for cp in self.CPlist:
            x1 = cp.img1x
            y1 = cp.img1y
            x2 = cp.img2x
            y2 = cp.img2y
            idp = str(cp.idp)

            if x1:
                symb1 = plt.Circle(
                    (x1, y1), ax11_units * 8, fill=False, color="red")
                symb2 = plt.Circle(
                    (x1, y1), ax11_units * 1, fill=True, color="red")
                self.ax11.text(x1 + ax11_units * 5, y1 + ax11_units * 5, idp)
                self.ax11.add_patch(symb1)
                self.ax11.add_patch(symb2)

            if x2:
                symb1 = plt.Circle(
                    (x2, y2), ax12_units * 8, fill=False, color="red")
                symb2 = plt.Circle(
                    (x2, y2), ax12_units * 1, fill=True, color="red")
                self.ax12.text(x2 + ax12_units * 5, y2 + ax12_units * 5, idp)
                self.ax12.add_patch(symb1)
                self.ax12.add_patch(symb2)

        self.fig.canvas.draw()

    def createConn(self):
        self.fig.canvas.mpl_connect("figure_enter_event", self.activeFigure)
        self.fig.canvas.mpl_connect("figure_leave_event", self.leftFigure)
        self.fig.canvas.mpl_connect("axes_enter_event", self.activeAxes)
        self.fig.canvas.mpl_connect("button_press_event", self.mouseClicked)
        self.ax11.callbacks.connect("xlim_changed", self.updateCanvas)
        self.ax12.callbacks.connect("xlim_changed", self.updateCanvas)

    def activeFigure(self, event):

        self.figureActive = True
        if self.pickmode and self.cursorGUI != "cross":
            self.cursorGUI = "cross"
            self.cursorChanged = True

    def leftFigure(self, event):

        self.figureActive = False
        if self.cursorGUI != "arrow":
            self.cursorGUI = "arrow"
            self.cursorChanged = True

    def activeAxes(self, event):
        self.axesActive = event.inaxes

    def mouseClicked(self, event):
        x = event.xdata
        y = event.ydata

        if self.toolbar.mode != "":
            self.pickmode = False

        if self.pickmode and (
            (event.inaxes == self.ax11) or (event.inaxes == self.ax12)
        ):

            if self.CPactive and not self.CPactive.status_complete:
                self.CPactive.appendCoord(x, y)
                self.cpChanged = True
            else:
                idp = self.lastIDP + 1
                cp = _ControlPoint(idp, x, y, self)
                self.CPlist.append(cp)
                self.cpChanged = True
                self.lastIDP += 1

            self.updateCanvas()


class _ControlPoint:
    def __init__(self, idp, x, y, other):
        self.img1x = None
        self.img1y = None
        self.img2x = None
        self.img2y = None
        self.status_complete = False
        self.idp = idp

        self.mn = other
        self.mn.CPactive = self

        self.appendCoord(x, y)

    def appendCoord(self, x, y):

        if self.mn.axesActive == self.mn.ax11 and self.img1x is None:
            self.img1x = x
            self.img1y = y
        elif self.mn.axesActive == self.mn.ax12 and self.img2x is None:
            self.img2x = x
            self.img2y = y

        else:
            raise Exception("Please, select control point in the other image.")

        if self.img1x and self.img2x:
            self.status_complete = True
            self.mn.cpActive = None

    @property
    def coord(self):
        return self.idp, self.img1x, self.img1y, self.img2x, self.img2y

    @property
    def coordText(self):
        if self.img1x and not self.img2x:
            return (
                str(round(self.idp, 2)),
                str(round(self.img1x, 2)),
                str(round(self.img1y, 2)),
                "",
                "",
            )
        elif not self.img1x and self.img2x:
            return (
                str(round(self.idp, 2)),
                "",
                "",
                str(round(self.img2x, 2)),
                str(round(self.img2y, 2)),
            )
        else:
            return (
                str(round(self.idp, 2)),
                str(round(self.img1x, 2)),
                str(round(self.img1y, 2)),
                str(round(self.img2x, 2)),
                str(round(self.img2y, 2)),
            )

    def __str__(self):
        return f"CP {self.idp}: {self.coord}"

    @property
    def getdict(self):

        dict = {
            "point_id": self.idp,
            "img1_x": self.img1x,
            "img1_y": self.img1y,
            "img2_x": self.img2x,
            "img2_y": self.img2y,
        }

        return dict


def point_coords(matched_points_dict):
    """Create source & destination coordinate numpy arrays from cpselect dict.

    Matched points is an array where:
    * the number of rows is equal to the number of points selected.
    * the first column is the point index label.
    * the second and third columns are the source x, y coordinates.
    * the last two columns are the destination x, y coordinates.

    Parameters
    ----------
    matched_points_dict : dict
        Dictionary returned from cpselect containing matched point coordinates.

    Returns
    -------
    (src, dst)
        Row, column coordaintes of source and destination matched points.
        Tuple contains two N x 2 ndarrays, where N is the number of points.
    """

    matched_points = np.array([list(point.values())
                               for point in matched_points_dict])
    src = np.flip(matched_points[:, 1:3], axis=1)  # flip for row, column index
    dst = np.flip(matched_points[:, 3:], axis=1)   # flip for row, column index

    return src, dst


def calculate_transform(src, dst, model=AffineTransform()):
    """Calculate transformation matrix from matched coordinate pairs.

    Parameters
    ----------
    src : ndarray
        Matched row, column coordinates from source image.
    dst : ndarray
        Matched row, column coordinates from destination image.
    model : scikit-image transformation class, optional.
        By default, model=AffineTransform()


    Returns
    -------
    ndarray
        Transformation matrix.
    """

    model.estimate(src, dst)
    print('Transformation matrix:')
    print(model.params)

    return model.params


def apply_transform(image, transformation, inverse=True, multichannel=True):
    """Apply transformation to a 2D image.

    Parameters
    ----------
    image : ndarray
        Input image array. 2D grayscale image expected, or
        2D plus color channels if multichannel kwarg is set to True.
    transformation : ndarray
        Affine transformation matrix. 3 x 3 shape.
    inverse : bool, optional
        Inverse transformation, eg: aligning source image coords to destination
        By default `inverse=True`.
    multichannel : bool, optional
        Treat the last dimension as color, transform each color separately.
        By default `multichannel=True`.

    Returns
    -------
    ndarray
        Image warped by transformation matrix.
    """

    if inverse:
        transformation = np.linalg.inv(transformation)

    if not multichannel:
        if image.ndim == 2:
            image = skimage.color.gray2rgb(image)
        elif image.ndim != transformation.shape[0] - 1:
            raise ValueError('Unexpected number of image dimensions for the '
                             'input transformation. Did you need to use: '
                             'multichannel=True ?')

    # move channel axis to the front for easier iteration over array
    image = np.moveaxis(image, -1, 0)
    warped_img = np.array([ndi.affine_transform((img_channel), transformation)
                           for img_channel in image])
    warped_img = np.moveaxis(warped_img, 0, -1)

    return warped_img


def overlay_images(fluorescence_image, fibsem_image, transparency=0.5):
    """Blend two RGB images together.

    Parameters
    ----------
    fluorescence_image : ndarray
        2D RGB image.
    fibsem_image : ndarray
        2D RGB image.
    transparency : float, optional
        Transparency alpha parameter between 0 - 1, by default 0.5

    Returns
    -------
    ndarray
        Blended 2D RGB image.
    """

    fluorescence_image = skimage.img_as_float(fluorescence_image)
    fibsem_image = skimage.img_as_float(fibsem_image)
    blended = transparency * fluorescence_image + (1 - transparency) * fibsem_image
    blended = np.clip(blended, 0, 1)

    return blended


def save_text(output_filename, transformation, matched_points_dict):
    """Save text summary of transformation matrix and image control points.

    Parameters
    ----------
    output_filename : str
        Filename for saving output overlay image file.
    transformation : ndarray
        Transformation matrix relating the two images.
    matched_points_dict : list of dict
        User selected matched control point pairs.

    Returns
    -------
    str
        Filename of output text file.
    """

    output_text_filename = os.path.splitext(output_filename)[0] + '.txt'
    with open(output_text_filename, 'w') as f:
        f.write(_timestamp() + '\n')
        f.write('PIEScope GUI version {}\n'.format(__version__))
        f.write('\nTRANSFORMATION MATRIX\n')
        f.write(str(transformation) + '\n')
        f.write('\nUSER SELECTED CONTROL POINTS\n')
        f.write(str(matched_points_dict) + '\n')

    return output_text_filename


def _timestamp():
    """Create timestamp string of current local time.

    Returns
    -------
    str
        Timestamp string
    """
    timestamp = time.strftime('%d-%b-%Y_%H-%M%p', time.localtime())
    return timestamp
