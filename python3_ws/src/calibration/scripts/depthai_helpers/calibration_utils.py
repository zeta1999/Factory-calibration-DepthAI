import cv2
import glob
import os
import shutil
import numpy as np
import re
import time
import consts.resource_paths
import json

# Creates a set of 13 polygon coordinates
def setPolygonCoordinates(height, width):
    horizontal_shift = width//4
    vertical_shift = height//4

    margin = 60
    slope = 150

    p_coordinates = [
            [[margin,0], [margin,height], [width//2, height-slope], [width//2, slope]],
            [[horizontal_shift, 0], [horizontal_shift, height], [width//2 + horizontal_shift, height-slope], [width//2 + horizontal_shift, slope]],
            [[horizontal_shift*2-margin, 0], [horizontal_shift*2-margin, height], [width//2 + horizontal_shift*2-margin, height-slope], [width//2 + horizontal_shift*2-margin, slope]],

            [[margin,margin], [margin, height-margin], [width-margin, height-margin], [width-margin, margin]],

            [[width-margin, 0], [width-margin, height], [width//2, height-slope], [width//2, slope]],
            [[width-horizontal_shift, 0], [width-horizontal_shift, height], [width//2-horizontal_shift, height-slope], [width//2-horizontal_shift, slope]],
            [[width-horizontal_shift*2+margin, 0], [width-horizontal_shift*2+margin, height], [width//2-horizontal_shift*2+margin, height-slope], [width//2-horizontal_shift*2+margin, slope]],

            [[0,margin], [width, margin], [width-slope, height//2], [slope, height//2]],
            [[0,vertical_shift], [width, vertical_shift], [width-slope, height//2+vertical_shift], [slope, height//2+vertical_shift]],
            [[0,vertical_shift*2-margin], [width, vertical_shift*2-margin], [width-slope, height//2+vertical_shift*2-margin], [slope, height//2+vertical_shift*2-margin]],

            [[0,height-margin], [width, height-margin], [width-slope, height//2], [slope, height//2]],
            [[0,height-vertical_shift], [width, height-vertical_shift], [width-slope, height//2-vertical_shift], [slope, height//2-vertical_shift]],
            [[0,height-vertical_shift*2+margin], [width, height-vertical_shift*2+margin], [width-slope, height//2-vertical_shift*2+margin], [slope, height//2-vertical_shift*2+margin]]
        ]
    return p_coordinates

def getPolygonCoordinates(idx, p_coordinates):
    return p_coordinates[idx]

def getNumOfPolygons(p_coordinates):
    return len(p_coordinates)

# Filters polygons to just those at the given indexes.
def select_polygon_coords(p_coordinates,indexes):
    if indexes == None:
        # The default
        return p_coordinates
    else:
        print("Filtering polygons to those at indexes=",indexes)
        return [p_coordinates[i] for i in indexes]

def image_filename(stream_name,polygon_index,total_num_of_captured_images):
    return "{stream_name}_p{polygon_index}_{total_num_of_captured_images}.png".format(stream_name=stream_name,polygon_index=polygon_index,total_num_of_captured_images=total_num_of_captured_images)

def polygon_from_image_name(image_name):
    """Returns the polygon index from an image name (ex: "left_p10_0.png" => 10)"""
    return int(re.findall("p(\d+)",image_name)[0])

class StereoCalibration(object):
    """Class to Calculate Calibration and Rectify a Stereo Camera."""

    def __init__(self):
        """Class to Calculate Calibration and Rectify a Stereo Camera."""

    def calibrate(self, filepath, square_size, out_filepath, flags):
        """Function to calculate calibration for stereo camera."""
        start_time = time.time()
        # init object data
        self.objp = np.zeros((9 * 6, 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2)
        for pt in self.objp:
            pt *= square_size

        # process images, detect corners, refine and save data
        self.process_images(filepath)

        # run calibration procedure and construct Homography and mesh
        self.stereo_calibrate_two_homography_calib()
        # save data to binary file

        R1_fp32 = self.R1.astype(np.float32)
        R2_fp32 = self.R2.astype(np.float32)
        M1_fp32 = self.M1.astype(np.float32)
        M2_fp32 = self.M2.astype(np.float32)
        R_fp32  = self.R.astype(np.float32)
        T_fp32  = self.T.astype(np.float32)
        M3_fp32 = np.zeros((3, 3), dtype = np.float32)
        R_rgb_fp32 = np.zeros((3, 3), dtype = np.float32) 
        T_rgb_fp32 = np.zeros(3, dtype = np.float32)  
        d1_coeff_fp32 = self.d1.astype(np.float32)
        d2_coeff_fp32 = self.d2.astype(np.float32)
        d3_coeff_fp32 = np.zeros(14, dtype = np.float32)
        print(out_filepath)
        with open(out_filepath, "wb") as fp:
            fp.write(R1_fp32.tobytes()) # goes to left camera
            fp.write(R2_fp32.tobytes()) # goes to right camera
            fp.write(M1_fp32.tobytes()) # left camera intrinsics
            fp.write(M2_fp32.tobytes()) # right camera intrinsics
            fp.write(R_fp32.tobytes()) # Rotation matrix left -> right
            fp.write(T_fp32.tobytes()) # Translation vector left -> right
            fp.write(M3_fp32.tobytes()) # rgb camera intrinsics ## Currently a zero matrix
            fp.write(R_rgb_fp32.tobytes()) # Rotation matrix left -> rgb ## Currently Identity matrix
            fp.write(T_rgb_fp32.tobytes()) # Translation vector left -> rgb ## Currently vector of zeros
            fp.write(d1_coeff_fp32.tobytes()) # distortion coeff of left camera
            fp.write(d2_coeff_fp32.tobytes()) # distortion coeff of right camera
            fp.write(d3_coeff_fp32.tobytes()) # distortion coeff of rgb camera - currently zeros

        if 0: # Print matrices, to compare with device data
            np.set_printoptions(suppress=True, precision=6)
            print("\nR1 (left)");  print(R1_fp32)
            print("\nR2 (right)"); print(R2_fp32)
            print("\nM1 (left)");  print(M1_fp32)
            print("\nM2 (right)"); print(M2_fp32)
            print("\nR");          print(R_fp32)
            print("\nT");          print(T_fp32)
            print("\nM3 (rgb)");   print(M3_fp32)

        if 0: # Print computed homography, to compare with device data
            np.set_printoptions(suppress=True, precision=6)
            for res_height in [800, 720, 400]:
                m1 = np.copy(M1_fp32)
                m2 = np.copy(M2_fp32)
                if res_height == 720:
                    m1[1,2] -= 40
                    m2[1,2] -= 40
                if res_height == 400:
                    m_scale = [[0.5,   0, 0],
                               [  0, 0.5, 0],
                               [  0,   0, 1]]
                    m1 = np.matmul(m_scale, m1)
                    m2 = np.matmul(m_scale, m2)
                h1 = np.matmul(np.matmul(m2, R1_fp32), np.linalg.inv(m1))
                h2 = np.matmul(np.matmul(m2, R2_fp32), np.linalg.inv(m2))
                h1 = np.linalg.inv(h1)
                h2 = np.linalg.inv(h2)
                print('\nHomography H1, H2 for height =', res_height)
                print(h1)
                print()
                print(h2)

        # self.create_save_mesh()
        
        # append specific flags to file
        # with open(out_filepath, "ab") as fp:
        #     fp.write(bytearray(flags))

        print("Calibration file written to %s." % (out_filepath))
        print("\tTook %i seconds to run image processing." % (round(time.time() - start_time, 2)))
        
        return self.test_epipolar(filepath)
        
        
    def process_images(self, filepath):
        """Read images, detect corners, refine corners, and save data."""
        # Arrays to store object points and image points from all the images.
        self.objpoints = []  # 3d point in real world space
        self.imgpoints_l = []  # 2d points in image plane.
        self.imgpoints_r = []  # 2d points in image plane.
        self.calib_successes = [] # polygon ids of left/right image sets with checkerboard corners.

        # images_left = glob.glob(filepath + "/left/*")
        # images_right = glob.glob(filepath + "/right/*")
        images_left = glob.glob(filepath + "/left/*")
        images_right = glob.glob(filepath + "/right/*")
        print("Images left path------------------->")
        print(images_left)
        images_left.sort()
        images_right.sort()

        print("\nAttempting to read images for left camera from dir: " +
              filepath + "/left/")
        print("Attempting to read images for right camera from dir: " +
              filepath + "/right/")

        assert len(images_left) != 0, "ERROR: Images not read correctly, check directory"
        assert len(images_right) != 0, "ERROR: Images not read correctly, check directory"

        self.temp_img_r_point_list = []
        self.temp_img_l_point_list = []

        for image_left, image_right in zip(images_left, images_right):
            img_l = cv2.imread(image_left, 0)
            img_r = cv2.imread(image_right, 0)


            assert img_l is not None, "ERROR: Images not read correctly"
            assert img_r is not None, "ERROR: Images not read correctly"

            print("Finding chessboard corners for %s and %s..." % (os.path.basename(image_left), os.path.basename(image_right)))
            start_time = time.time()

            # Find the chess board corners
            flags = 0
            flags |= cv2.CALIB_CB_ADAPTIVE_THRESH
            flags |= cv2.CALIB_CB_NORMALIZE_IMAGE
            ret_l, corners_l = cv2.findChessboardCorners(img_l, (9, 6), flags)
            ret_r, corners_r = cv2.findChessboardCorners(img_r, (9, 6), flags)

            # termination criteria
            self.criteria = (cv2.TERM_CRITERIA_MAX_ITER +
                             cv2.TERM_CRITERIA_EPS, 30, 0.001)

            # if corners are found in both images, refine and add data
            if ret_l and ret_r:
                self.objpoints.append(self.objp)
                rt = cv2.cornerSubPix(img_l, corners_l, (5, 5),
                                      (-1, -1), self.criteria)
                self.imgpoints_l.append(corners_l)
                rt = cv2.cornerSubPix(img_r, corners_r, (5, 5),
                                      (-1, -1), self.criteria)
                self.imgpoints_r.append(corners_r)
                self.temp_img_l_point_list.append([corners_l])
                self.temp_img_r_point_list.append([corners_r])
                self.calib_successes.append(polygon_from_image_name(image_left))
                print("\t[OK]. Took %i seconds." % (round(time.time() - start_time, 2)))
            else:
                print("\t[ERROR] - Corners not detected. Took %i seconds." % (round(time.time() - start_time, 2)))

            self.img_shape = img_r.shape[::-1]
        print(str(len(self.objpoints)) + " of " + str(len(images_left)) +
              " images being used for calibration")
        self.ensure_valid_images()

    def ensure_valid_images(self):
        """
        Ensures there is one set of left/right images for each polygon. If not, raises an raises an
        AssertionError with instructions on re-running calibration for the invalid polygons.
        """
        expected_polygons = len(setPolygonCoordinates(1000,600)) # inseted values are placeholders
        unique_calib_successes = set(self.calib_successes)
        if len(unique_calib_successes) != expected_polygons:
            valid = set(np.arange(0,expected_polygons))
            missing = valid - unique_calib_successes
            arg_value = ' '.join(map(str, missing))
            raise AssertionError("Missing valid image sets for %i polygons. Re-run calibration with the\n'-p %s' argument to re-capture images for these polygons." % (len(missing), arg_value))
        else:
            return True
    
    def stereo_calibrate_two_homography_calib(self):
        """Calibrate camera and construct Homography."""
        # init camera calibrations
        rt, self.M1, self.d1, self.r1, self.t1 = cv2.calibrateCamera(
            self.objpoints, self.imgpoints_l, self.img_shape, None, None)
        rt, self.M2, self.d2, self.r2, self.t2 = cv2.calibrateCamera(
            self.objpoints, self.imgpoints_r, self.img_shape, None, None)

        # config
        flags = 0
        #flags |= cv2.CALIB_FIX_ASPECT_RATIO
        flags |= cv2.CALIB_USE_INTRINSIC_GUESS
        #flags |= cv2.CALIB_SAME_FOCAL_LENGTH
        #flags |= cv2.CALIB_ZERO_TANGENT_DIST
        flags |= cv2.CALIB_RATIONAL_MODEL
        #flags |= cv2.CALIB_FIX_K1
        #flags |= cv2.CALIB_FIX_K2
        #flags |= cv2.CALIB_FIX_K3
        #flags |= cv2.CALIB_FIX_K4
        #flags |= cv2.CALIB_FIX_K5
        #flags |= cv2.CALIB_FIX_K6
        #flags |= cv::CALIB_ZERO_TANGENT_DIST

        stereocalib_criteria = (cv2.TERM_CRITERIA_COUNT +
                                cv2.TERM_CRITERIA_EPS, 100, 1e-5)

        # stereo calibration procedure
        ret, self.M1, self.d1, self.M2, self.d2, self.R, self.T, E, F = cv2.stereoCalibrate(
            self.objpoints, self.imgpoints_l, self.imgpoints_r,
            self.M1, self.d1, self.M2, self.d2, self.img_shape,
            criteria=stereocalib_criteria, flags=flags)

        self.R1, self.R2, self.P1, self.P2, self.Q, validPixROI1, validPixROI2 = cv2.stereoRectify(
                                                                                                self.M1,
                                                                                                self.d1,
                                                                                                self.M2,
                                                                                                self.d2,
                                                                                                self.img_shape, self.R, self.T)

        self.H1 = np.matmul(np.matmul(self.M2, self.R1), np.linalg.inv(self.M1))
        self.H2 = np.matmul(np.matmul(self.M2, self.R2), np.linalg.inv(self.M2))                                                                                        


    def test_epipolar(self, dataset_dir):
        images_left = glob.glob(dataset_dir + '/left/*.png')
        images_right = glob.glob(dataset_dir + '/right/*.png')
        images_left.sort()
        images_right.sort()
        assert len(images_left) != 0, "ERROR: Images not read correctly"
        assert len(images_right) != 0, "ERROR: Images not read correctly"

        image_data_pairs = []
        for image_left, image_right in zip(images_left, images_right):
            # read images
            img_l = cv2.imread(image_left, 0)
            img_r = cv2.imread(image_right, 0)
            # warp right image
            img_l = cv2.warpPerspective(img_l, self.H1, img_l.shape[::-1],
                                        cv2.INTER_CUBIC +
                                        cv2.WARP_FILL_OUTLIERS +
                                        cv2.WARP_INVERSE_MAP)
            
            img_r = cv2.warpPerspective(img_r, self.H2, img_r.shape[::-1],
                                        cv2.INTER_CUBIC +
                                        cv2.WARP_FILL_OUTLIERS +
                                        cv2.WARP_INVERSE_MAP)


            image_data_pairs.append((img_l, img_r))


        # compute metrics
        imgpoints_r = []
        imgpoints_l = []
        for image_data_pair in image_data_pairs:
            flags = 0
            flags |= cv2.CALIB_CB_ADAPTIVE_THRESH
            flags |= cv2.CALIB_CB_NORMALIZE_IMAGE
            flags |= cv2.CALIB_CB_FAST_CHECK
            ret_l, corners_l = cv2.findChessboardCorners(image_data_pair[0],
                                                         (9, 6), flags)
            ret_r, corners_r = cv2.findChessboardCorners(image_data_pair[1],
                                                         (9, 6), flags)

            # termination criteria
            self.criteria = (cv2.TERM_CRITERIA_MAX_ITER +
                             cv2.TERM_CRITERIA_EPS, 10, 0.05)

            # if corners are found in both images, refine and add data
            if ret_l and ret_r:
                rt = cv2.cornerSubPix(image_data_pair[0], corners_l, (5, 5),
                                      (-1, -1), self.criteria)
                rt = cv2.cornerSubPix(image_data_pair[1], corners_r, (5, 5),
                                      (-1, -1), self.criteria)
                imgpoints_l.extend(corners_l)
                imgpoints_r.extend(corners_r)
                epi_error_sum = 0
                for l_pt, r_pt in zip(corners_l, corners_r):
                    epi_error_sum += abs(l_pt[0][1] - r_pt[0][1])
                
                # print("Average Epipolar Error per image on host: " + str(epi_error_sum / len(corners_l)))

        epi_error_sum = 0
        for l_pt, r_pt in zip(imgpoints_l, imgpoints_r):
            epi_error_sum += abs(l_pt[0][1] - r_pt[0][1])

        avg_epipolar = epi_error_sum / len(imgpoints_r)
        print("Average Epipolar Error: " + str(avg_epipolar))

        return avg_epipolar

        # if avg_epipolar > 0.5:
        #     fail_img = cv2.imread(consts.resource_paths.calib_fail_path, cv2.IMREAD_COLOR)
        #     cv2.imshow('Calibration test Failed', fail_img)
        # else:            
        #     self.rundepthai()
        #     if not depthai.init_device(consts.resource_paths.device_cmd_fpath, ''):
        #         print("Error initializing device. Try to reset it.")
        #         exit(1)
            
        #     if depthai.is_eeprom_loaded():
        #         pass_img = cv2.imread(consts.resource_paths.pass_path, cv2.IMREAD_COLOR)
        #         while (1):
        #             cv2.imshow('Calibration test Passed and wrote to EEPROM', pass_img)
        #             k = cv2.waitKey(33)
        #             if k == 32 or k == 27:  # Esc key to stop
        #                 break
        #             elif k == -1:  # normally -1 returned,so don't print it
        #                 continue
        #     else:
        #         fail_img = cv2.imread(consts.resource_paths.eeprom_fail_path, cv2.IMREAD_COLOR)
        #         while (1):
        #             cv2.imshow('EEPROM write failed', fail_img)
        #             k = cv2.waitKey(33)
        #             if k == 32 or k == 27:  # Esc key to stop
        #                 break
        #             elif k == -1:  # normally -1 returned,so don't print it
        #                 continue
        #     depthai.deinit_device()
