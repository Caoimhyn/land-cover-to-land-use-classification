import gdal
import sys
import time as tm
import numpy as np
import scipy
import scipy.stats
from gdalconst import *
from skimage import exposure
from skimage import io
from sklearn import tree
from matplotlib import pyplot as plt
from matplotlib import colors


def open_image(directory):
    image_ds = gdal.Open(directory, GA_ReadOnly)

    if image_ds is None:
        print 'Could not open ' + directory
        sys.exit(1)

    return image_ds


def get_img_param(image_dataset):
    cols = image_dataset.RasterXSize
    rows = image_dataset.RasterYSize
    num_bands = image_dataset.RasterCount
    img_gt = image_dataset.GetGeoTransform()
    img_proj = image_dataset.GetProjection()
    img_driver = image_dataset.GetDriver()

    img_params = [cols, rows, num_bands, img_gt, img_proj, img_driver]

    return img_params


def output_ds(out_array, img_params, fn='result.tif'):
    # create output raster data-set
    cols = img_params[0]
    rows = img_params[1]
    bands = 1  # ndvi image needs only one band
    gt = img_params[3]
    proj = img_params[4]
    driver = gdal.GetDriverByName('GTiff')
    driver.Register()

    out_ras = driver.Create(fn, cols, rows, bands, GDT_Float32)
    out_ras.SetGeoTransform(gt)
    out_ras.SetProjection(proj)

    out_band = out_ras.GetRasterBand(1)

    out_band.WriteArray(out_array)

    out_band.SetNoDataValue(0)
    out_band.FlushCache()
    out_band.GetStatistics(0, 1)

    return


def compute_ndvi(image, img_params):
    print '\ncomputing ndvi...'
    # create output raster data-set
    cols = img_params[0]
    rows = img_params[1]
    bands = 1  # the ndvi output image needs only 1 band
    gt = img_params[3]
    proj = img_params[4]
    driver = img_params[5]

    out_ras = driver.Create('wv2_ndvi.tif', cols, rows, bands, GDT_Float32)
    out_ras.SetGeoTransform(gt)
    out_ras.SetProjection(proj)

    out_band = out_ras.GetRasterBand(1)

    x_bsize = 5000
    y_bsize = 5000

    ir_band = image.GetRasterBand(3)
    nir_band = image.GetRasterBand(4)

    for i in range(0, rows, y_bsize):
        if i + y_bsize < rows:
            num_rows = y_bsize
        else:
            num_rows = rows - i
        for j in range(0, cols, x_bsize):
            if j + x_bsize < cols:
                num_cols = x_bsize
            else:
                num_cols = cols - j

            ir_array = ir_band.ReadAsArray(j, i, num_cols, num_rows).\
                astype(np.float16)
            nir_array = nir_band.ReadAsArray(j, i, num_cols, num_rows).\
                astype(np.float16)

            mask = np.greater(ir_array + nir_array, 0)
            ndvi = np.choose(mask, (-99, (nir_array - ir_array) / (nir_array + ir_array)))

            out_band.WriteArray(ndvi, j, i)

    out_band.SetNoDataValue(-99)
    out_band.FlushCache()
    out_band.GetStatistics(0, 1)

    return


def main():
    # Open Landsat
    wv2_dir = r"naga_cloudmasked.tif"

    wv2_img = open_image(wv2_dir)

    # retrieve image parameters
    wv2_param = get_img_param(wv2_img)
    #print landsat_param

    # compute landsat ndvi
    compute_ndvi(wv2_img, wv2_param)


if __name__ == "__main__":
    start = tm.time()
    main()
    print 'Processing time: %f seconds' % (tm.time() - start)
