# The following script was derived from the journal article
# A Comparison of Two Spectral Mixture Modelling Approaches for
# Impervious Surface Area Mapping In Urban Areas

import gdal
import sys
import glob
import os
import time as tm
import numpy as np
import scipy
import scipy.ndimage
import scipy.stats
import random
from gdalconst import *
from matplotlib import pyplot as plt
from subprocess import call


def open_image(directory):
    """
    Helper function.
    Opens image and returns
    gdal MajorObject
    """
    image_ds = gdal.Open(directory, GA_ReadOnly)

    if image_ds is None:
        print 'Could not open ' + directory
        sys.exit(1)

    return image_ds


def get_img_param(image_dataset):
    """
    Helper function.
    Collects image parameters
    returns them as a list.
    """
    cols = image_dataset.RasterXSize
    rows = image_dataset.RasterYSize
    num_bands = image_dataset.RasterCount
    img_gt = image_dataset.GetGeoTransform()
    img_proj = image_dataset.GetProjection()
    img_driver = image_dataset.GetDriver()

    img_params = [cols, rows, num_bands, img_gt, img_proj, img_driver]

    return img_params


def output_ds(out_array, img_params, d_type=GDT_Unknown, fn='result.tif'):
    """
    Helper function.
    Writes new data-set into disk
    and saves output arrays in the data-set.
    """
    gdal_data_types = [
                GDT_Byte,
                GDT_CFloat32,
                GDT_CFloat64,
                GDT_CInt16,
                GDT_CInt32,
                GDT_Float32,
                GDT_Float64,
                GDT_Int16,
                GDT_Int32,
                GDT_UInt16,
                GDT_UInt32,
                GDT_Unknown,
                ]

    numpy_data_types = [
                        'bool',
                        'int8',
                        'int16',
                        'int32',
                        'int64',
                        'uint8',
                        'uint16',
                        'uint32',
                        'uint64',
                        'float16',
                        'float32',
                        'float64'
                        ]

    # create output raster data-set
    cols = img_params[0]
    rows = img_params[1]
    bands = 1  # ndvi image needs only one band
    gt = img_params[3]
    proj = img_params[4]
    driver = gdal.GetDriverByName('GTiff')
    driver.Register()

    out_ras = driver.Create(fn, cols, rows, bands, d_type)
    out_ras.SetGeoTransform(gt)
    out_ras.SetProjection(proj)

    out_band = out_ras.GetRasterBand(1)

    out_band.WriteArray(out_array)

    out_band.SetNoDataValue(0)
    out_band.FlushCache()
    out_band.GetStatistics(0, 1)

    return


def downscale_image(hires_img, lores_param):
    """
    Takes in a high resolution image and resamples it
    to a lower resolution.
    The parameters are taken from a low resolution
    reference image that are used to compute the extent
    and resolution of the resampled data-set.
    """

    # collect columns, rows, extent, resolution and geotrans, and proj of img to be masked
    cols = lores_param[0]
    rows = lores_param[1]
    geotrans = lores_param[3]

    # unpack geotransform parameters
    topleft_x = geotrans[0]
    topleft_y = geotrans[3]
    x = geotrans[1]
    y = geotrans[5]

    # compute extents
    x_min = topleft_x
    y_min = topleft_y + y*rows
    x_max = topleft_x + x*cols
    y_max = topleft_y

    downsample_cmd = [
                      'gdalwarp',
                      '-r', 'average',  # use average as sampling algorithm
                      '-te',  # specify extent
                      str(x_min), str(y_min),
                      str(x_max), str(y_max),
                      '-ts',  # specify the number of columns and rows
                      str(cols), str(rows),
                      hires_img,
                      'wv2_ndvi_resampled.tif'
                      ]

    call(downsample_cmd)

    return


def temporal_mask(X, Y, X_img_param):  # TODO: make save intermediate data to disk optional
    """
    Masks out pixels that underwent change between
    the capture dates of the image datasets.
    Assumes parameters are arrays of equal shape.
    -------------------------------------------------
    1. First apply masks of equal shape and elements
    to the dependent and independent datasets.
    2. Create training samples by random sampling the
    dataset pair with an arbitrary sample size.
    3. Generate model from the training samples.
    4. Predict image from model using the pixels of the
    independent dataset.
    5. Generate residual image.
    6. Compute the standard deviation of the residual image.
    7. Generate and apply image mask by selecting pixels
    from the masked original dependent variable.
    -------------------------------------------------
    The pixels that will be used for regression from
    the training data must be carefully filtered.
    Numerical nodata values from the GDAL image datasets
    must be converted into NaN so that they do not
    interfere with model training.
    """

    ndvi_1 = X.GetRasterBand(1).ReadAsArray(0, 0)  # wv2 ndvi
    ndvi_2 = Y.GetRasterBand(1).ReadAsArray(0, 0)  # landsat ndvi

    # no value elements interfere with the regression
    # so they need to be masked out by
    # converting them to nan
    # they must not be converted into a number
    ndvi_1[ndvi_1 == -99.] = np.nan
    ndvi_2[ndvi_2 == -99.] = np.nan

    # the number of valid elements for regression must be
    # the same for both image arrays hence novalue
    # masks of each image must be applied to other

    # apply novalue mask of image 2 to image 1
    ndvi_1_masked = np.where(np.isnan(ndvi_2), np.nan, ndvi_1)  # apply novalue mask of 2nd image
    ndvi_1_flat = ndvi_1_masked[np.isnan(ndvi_1_masked)==False]

    # apply novalue mask of image 1 to image 2
    ndvi_2_masked = np.where(np.isnan(ndvi_1), np.nan, ndvi_2)  # apply novalue mask of 1st image
    ndvi_2_flat = ndvi_2_masked[np.isnan(ndvi_2_masked)==False]

    # random sample of pixels
    sample_pixels = random.sample(zip(ndvi_1_flat, ndvi_2_flat), 3000)  # the sample size suggested by article

    training_list_x = []
    training_list_y = []

    for i in range(len(sample_pixels)):
        training_list_x.append(sample_pixels[i][0])
        training_list_y.append(sample_pixels[i][1])

    training_sample_x = np.array(training_list_x)
    training_sample_y = np.array(training_list_y)

    # apply scipy linear regression to samples
    slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(training_sample_x, training_sample_y)
    print '\nslope: %f' % slope
    print 'intercept: %f' % intercept
    print 'R value: %f' % r_value
    print 'p value: %f' % p_value
    print 'error: %f' % std_err

    model = slope * training_sample_x + intercept

    # plot samples and regression line
    fig, ax = plt.subplots()
    plt.title('NDVI Values of Worldview 2 and Landsat 8')
    # plt.plot(training_sample_x, training_sample_y, 'g.', training_sample_x, model, 'k-', lw=2)
    ax.scatter(training_sample_x, training_sample_y, color='g' , marker='.', alpha=.4)
    plt.plot(training_sample_x, model, 'k-', lw=2)
    ax.set_ylabel('NDVI Landsat8')
    ax.set_xlabel('Average NDVI Worldview2')
    plt.savefig('plot.png')

    # predict landsat image from regression model
    predicted_image = slope * ndvi_1_masked + intercept
    output_ds(predicted_image, X_img_param, GDT_Float32, 'predicted_ndvi.tif')

    # generate residual image
    residual_image = ndvi_2_masked - predicted_image
    output_ds(residual_image, X_img_param, GDT_Float32, 'residual_image.tif')

    # compute standard deviation of residual image, ignoring nan values
    std_residual = np.nanstd(residual_image)

    print '\nstandard deviation of residual landsat image is: %f' % std_residual

    # generate mask by threshold
    # set nodata value to 0 so that it does not interfere in the following step
    residual_image[np.isnan(residual_image)] = 0.
    mask = np.where(np.less(residual_image, std_residual*1.75), np.array(1), np.array(0)).\
        astype(bool)
    output_ds(mask, X_img_param, GDT_Byte, 'mask.tif')

    print 'thresholding landsat ndvi image with 2x the standard deviation of residual image...'
    # apply mask to first image

    ndvi_1_masked = np.where(mask == 1, ndvi_1_masked, np.nan)
    output_ds(ndvi_1_masked, X_img_param, GDT_Float32, 'landsat_ndvi_masked.tif')

    # TODO: memory management

    return


def main():
    # Open Landsat and WV2 ndvi images
    landsat_dir = "landsat_ndvi.tif"
    wv2_dir = "wv2_ndvi.tif"

    landsat_img = open_image(landsat_dir)
    wv2_img = open_image(wv2_dir)

    # retrieve image parameters
    landsat_param = get_img_param(landsat_img)
    # print 'Landsat8 image has: \n%d columns\n%d rows' % (landsat_param[0], landsat_param[1])
    wv2_param = get_img_param(wv2_img)
    # print '\nWorldview2 image has: \n%d columns\n%d rows' % (wv2_param[0], wv2_param[1])

    # downscale wv2 image
    # print '\nDownscaling...'
    # downscale_image(wv2_dir, landsat_param)

    # collect ndvi images
    print '\nCreating temporal mask...'
    cwd = os.getcwd()
    wv2_resampled = None
    for f in glob.glob(cwd + '\*_resampled.tif'):  # search for the resampled wv2 ndvi file
        wv2_resampled = gdal.Open(f, GA_ReadOnly)

        # Worldview2 pixels are the independent variables
        # Landsat pixels are the dependent variables

    temporal_mask(wv2_resampled, landsat_img, landsat_param)

    #output_ds(predicted_landsat, landsat_param, 'mask.tif')

    # create temporal mask

if __name__ == "__main__":
    start = tm.time()
    main()
    print '\nProcessing time: %f seconds' % (tm.time() - start)
