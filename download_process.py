import argparse
import io
import os
import subprocess

import ray
import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
#import tensorflow as tf
from PIL import Image
from psutil import cpu_count
tf.disable_v2_behavior()
from utils import *
from object_detection.utils import dataset_util, label_map_util

label_map = label_map_util.load_labelmap('./label_map.pbtxt')
label_map_dict = label_map_util.get_label_map_dict(label_map)
t2idict = {y:x for x,y in label_map_dict.items()}
def class_text_to_int(text):
    return t2idict[text]

def create_tf_example(filename, encoded_jpeg, annotations):
    """
    This function create a tf.train.Example from the Waymo frame.

    args:
        - filename [str]: name of the image
        - encoded_jpeg [bytes]: jpeg encoded image
        - annotations [protobuf object]: bboxes and classes

    returns:
        - tf_example [tf.Train.Example]: tf example in the objection detection api format.
    """

    # TODO: Implement function to convert the data
    encoded_jpg_io = io.BytesIO(encoded_jpeg)
    image = Image.open(encoded_jpg_io)
    width, height = image.size
    
    image_format = b'jpeg'
    
    xmins = []
    xmaxs = []
    ymins = []
    ymaxs = []
    classes_text = []
    classes = []
    
    for index, row in enumerate(annotations):
        
        xmin = row.box.center_x - row.box.length/2.0
        xmax = row.box.center_x + row.box.length/2.0
        ymin = row.box.center_y - row.box.width/2.0
        ymax = row.box.center_y + row.box.width/2.0
        
         
        xmins.append(xmin / width)
        xmaxs.append(xmax / width)
        ymins.append(ymin / height)
        ymaxs.append(ymax / height)
        classes_text.append(class_text_to_int(row.type).encode('utf8'))
        classes.append(row.type)

    filename = filename.encode('utf8')
    tf_example = tf.train.Example(features=tf.train.Features(feature={
        'image/height': int64_feature(height),
        'image/width': int64_feature(width),
        'image/filename': bytes_feature(filename),
        'image/source_id': bytes_feature(filename),
        'image/encoded': bytes_feature(encoded_jpeg),
        'image/format': bytes_feature(image_format),
        'image/object/bbox/xmin': float_list_feature(xmins),
        'image/object/bbox/xmax': float_list_feature(xmaxs),
        'image/object/bbox/ymin': float_list_feature(ymins),
        'image/object/bbox/ymax': float_list_feature(ymaxs),
        'image/object/class/text': bytes_list_feature(classes_text),
        'image/object/class/label': int64_list_feature(classes),
    }))
    return tf_example


def download_tfr(filepath, temp_dir):
    """
    download a single tf record 

    args:
        - filepath [str]: path to the tf record file
        - temp_dir [str]: path to the directory where the raw data will be saved

    returns:
        - local_path [str]: path where the file is saved
    """
    # create data dir
    dest = os.path.join(temp_dir, 'raw')
    os.makedirs(dest, exist_ok=True)
    filename = os.path.basename(filepath)
    local_path = os.path.join(dest, filename)
    if os.path.exists(local_path):
        return local_path
    print("start downloading {}".format(local_path))
    # download the tf record file
    #cmd = ['gsutil', 'cp', filepath, f'{dest}']
    #logger.info(f'Downloading {filepath}')
    #res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #if res.returncode != 0:
    #    logger.error(f'Could not download file {filepath}') 
    
    
    #print("complete downloading {}".format(local_path))
    return local_path


def process_tfr(filepath, data_dir):
    """
    process a Waymo tf record into a tf api tf record

    args:
        - filepath [str]: path to the Waymo tf record file
        - data_dir [str]: path to the destination directory
    """
    # create processed data dir
    dest = os.path.join(data_dir, 'processed')
    os.makedirs(dest, exist_ok=True)
    file_name = os.path.basename(filepath)
    
    if os.path.exists(f'{dest}/{file_name}'):
        return

    logger.info(f'Processing {filepath}')
    writer = tf.python_io.TFRecordWriter(f'{dest}/{file_name}')
    dataset = tf.data.TFRecordDataset(filepath, compression_type='')
    for idx, data in enumerate(dataset):
        frame = open_dataset.Frame()
        frame.ParseFromString(bytearray(data.numpy()))
        encoded_jpeg, annotations = parse_frame(frame)
        filename = file_name.replace('.tfrecord', f'_{idx}.tfrecord')
        tf_example = create_tf_example(filename, encoded_jpeg, annotations)
        writer.write(tf_example.SerializeToString())
    writer.close()
    return


@ray.remote
def download_and_process(filename, temp_dir, data_dir):
    # need to re-import the logger because of multiprocesing
    dest = os.path.join(data_dir, 'processed')
    os.makedirs(dest, exist_ok=True)
    file_name = os.path.basename(filename)
    
    if os.path.exists(f'{dest}/{file_name}'):
        print("processed file  {} exists, skip".format(file_name))
        return
    logger = get_module_logger(__name__)
    local_path = download_tfr(filename, temp_dir)
    #local_path = "/app/project/training_0000"
    process_tfr(local_path, data_dir)
    # remove the original tf record to save space
    #if os.path.exists(local_path):
    #    logger.info(f'Deleting {local_path}')
    #    os.remove(local_path)


if __name__ == "__main__": 
    parser = argparse.ArgumentParser(description='Download and process tf files')
    parser.add_argument('--data_dir', required=False, default="./data",
                        help='processed data directory')
    parser.add_argument('--temp_dir', required=False, default="/app/project/training_0000",
                        help='raw data directory')
    args = parser.parse_args()
    logger = get_module_logger(__name__)
    # open the filenames file
    with open('filenames1.txt', 'r') as f:
        filenames = f.read().splitlines() 
    logger.info(f'Download {len(filenames)} files. Be patient, this will take a long time.')
    
    data_dir = args.data_dir
    temp_dir = args.temp_dir
    
#     download_and_process(filenames[0], temp_dir, data_dir)
    # init ray
    ray.init(num_cpus=cpu_count())
  
    workers = [download_and_process.remote(fn, temp_dir, data_dir) for fn in filenames[:100]]
    _ = ray.get(workers)
    print("Done with downloading")



