import re
import sys
import datetime
import scipy
import numpy as np
import pandas as pd
import cv2
import dicom
import os
import glob
import math
import time
import uuid
from datetime import timedelta
import matplotlib
# Force matplotlib to not use any Xwindows backend, so that you can output graphs
matplotlib.use('Agg')
from sklearn import model_selection, metrics
from matplotlib import pyplot as plt
import tensorflow as tf
from tqdm import tqdm

# Fixes "SettingWithCopyWarning: A value is trying to be set on a copy of a slice from a DataFrame"
pd.options.mode.chained_assignment = None

def img_to_rgb(im):
    x, y, z = im.shape
    ret = np.empty((x, y, z, 1), dtype=np.float32)
    ret[:, :, :, 0] = im
    return ret

def get_ids(PATH):
    ids = []
    for path in glob.glob(PATH + '*_X.npy'):
        chunk_id = re.match(r'([0-9a-f-]+)_X.npy', os.path.basename(path)).group(1)
        ids.append(chunk_id)
    return ids

def get_data(chunk_ids, PATH):
    X = np.asarray(chunk_ids)
    Y = np.ndarray([len(chunk_ids)], dtype=np.float32)

    count = 0
    for chunk_id in chunk_ids:
        y = np.load(PATH + chunk_id + '_Y.npy').astype(np.float32, copy=False)
        Y[count] = y
        count = count + 1

    return X, Y

def conv3d(inputs,             # The previous layer.
           filter_size,        # Width and height of each filter.
           num_filters,        # Number of filters.
           num_channels,       # 1
           strides,            # [1,1,1,1,1]
           layer_name):
    with tf.name_scope(layer_name):
        with tf.name_scope('weights'):
            filters = tf.get_variable(layer_name + 'weights', shape = [filter_size, filter_size, filter_size, num_channels, num_filters],
                                      initializer = tf.truncated_normal_initializer(stddev=1e-1, dtype=tf.float32),
                                      regularizer = tf.contrib.layers.l2_regularizer(FLAGS.reg_constant))
        with tf.name_scope('biases'):
            biases = tf.Variable(tf.constant(0.0, shape=[num_filters], dtype=tf.float32))
        with tf.name_scope('conv'):
            conv = tf.nn.conv3d(inputs, filters, strides, padding='SAME')
        out = tf.nn.bias_add(conv, biases)
        return out, filters

def max_pool_3d(inputs,
                filter_size,
                strides,
                layer_name):
    with tf.name_scope(layer_name):
        return tf.nn.max_pool3d(inputs,
                                ksize=filter_size,
                                strides=strides,
                                padding='SAME',
                                name='max_pool')

def dropout_3d(inputs,
               keep_prob,
               layer_name):
    with tf.name_scope(layer_name):
        return tf.nn.dropout(inputs, keep_prob, name='dropout')

def flatten_3d(layer, layer_name):
    with tf.name_scope(layer_name):
        layer_shape = layer.get_shape()
        num_features = layer_shape[1:5].num_elements()
        layer_flat = tf.reshape(layer, [-1, num_features])
        return layer_flat, num_features

def relu_3d(inputs,
            layer_name):
    with tf.name_scope(layer_name):
        return tf.nn.relu(inputs, name='relu')

def dense_3d(inputs,
             num_inputs,
             num_outputs,
             layer_name):
    with tf.name_scope(layer_name):
        with tf.name_scope('weights'):
            weights = tf.get_variable(layer_name + 'weights', shape = [num_inputs, num_outputs],
                              initializer = tf.truncated_normal_initializer(stddev=1e-1, dtype=tf.float32),
                              regularizer = tf.contrib.layers.l2_regularizer(FLAGS.reg_constant))
        with tf.name_scope('biases'):
            biases = tf.Variable(tf.constant(0.0, shape=[num_outputs], dtype=tf.float32))
        with tf.name_scope('Wx_plus_b'):
            layer = tf.matmul(inputs, weights) + biases
        return layer

def get_batch(x, y):
    num_images = len(x)
    idx = np.random.choice(num_images,
                           size=FLAGS.batch_size,
                           replace=False)
    x_batch_ids = x[idx]
    y_batch = y[idx]

    x_batch = np.ndarray([FLAGS.batch_size, FLAGS.chunk_size, FLAGS.chunk_size, FLAGS.chunk_size, 1], dtype=np.float32)

    count = 0
    for chunk_id in x_batch_ids:
        chunk = np.load(DATA_PATH + chunk_id + '_X.npy').astype(np.float32, copy=False)
        x_batch[count, :, :, :, :] = img_to_rgb(chunk)
        count = count + 1

    return x_batch, y_batch

def save_model(sess, model_id, saver):
    checkpoint_folder = os.path.join(MODELS, model_id)
    if not os.path.exists(checkpoint_folder):
        os.makedirs(checkpoint_folder)
    save_path = os.path.join(checkpoint_folder, 'model')
    saver.save(sess=sess, save_path=save_path)

def train_3d_nn():
    time0 = time.time()
    chunks_ids = get_ids(DATA_PATH)
    X, Y = get_data(chunks_ids, DATA_PATH)

    print('X.shape', X.shape)
    print('Y.shape', Y.shape)
    print('np.bincount(Y)', np.bincount(Y.astype(dtype=np.int64)))

    non_zero_nodules = Y != 0.0
    X = X[non_zero_nodules]
    Y = Y[non_zero_nodules]

    #print(Y_merge_class_3_2)
    #X = X[Y_merge_class_3_2]
    #Y = Y[Y_merge_class_3_2]

    # print('X.shape', X.shape)
    # print('Y.shape', Y.shape)
    # print('np.bincount(Y)', np.bincount(Y.astype(dtype=np.int64)))

    # SAMPLE_SIZE = 60

    # x = np.ndarray((SAMPLE_SIZE*6), dtype=np.object)
    # y = np.ndarray((SAMPLE_SIZE*6), dtype=np.float32)

    # x[0:SAMPLE_SIZE] = X[Y==0.0][0:SAMPLE_SIZE]
    # x[SAMPLE_SIZE: SAMPLE_SIZE*2] = X[Y==1.0][0:SAMPLE_SIZE]
    # x[SAMPLE_SIZE*2:SAMPLE_SIZE*3] = X[Y==2.0][0:SAMPLE_SIZE]
    # x[SAMPLE_SIZE*3:SAMPLE_SIZE*4] = X[Y==3.0][0:SAMPLE_SIZE]
    # x[SAMPLE_SIZE*4:SAMPLE_SIZE*5] = X[Y==4.0][0:SAMPLE_SIZE]
    # x[SAMPLE_SIZE*5:SAMPLE_SIZE*6] = X[Y==5.0][0:SAMPLE_SIZE]

    # y[0:SAMPLE_SIZE] = [0.0]*SAMPLE_SIZE
    # y[SAMPLE_SIZE:SAMPLE_SIZE*2] = [1.0]*SAMPLE_SIZE
    # y[SAMPLE_SIZE*2:SAMPLE_SIZE*3] = [2.0]*SAMPLE_SIZE
    # y[SAMPLE_SIZE*3:SAMPLE_SIZE*4] = [3.0]*SAMPLE_SIZE
    # y[SAMPLE_SIZE*4:SAMPLE_SIZE*5] = [4.0]*SAMPLE_SIZE
    # y[SAMPLE_SIZE*5:SAMPLE_SIZE*6] = [5.0]*SAMPLE_SIZE

    # print(x)
    # print(y)
    # print('Using SAMPLE_SIZE', SAMPLE_SIZE)
    # print('x.shape', x.shape)
    # print('y.shape', y.shape)

    print("Total time to load data: " + str(timedelta(seconds=int(round(time.time() - time0)))))
    print('Splitting into train, validation sets')

    train_x, validation_x, train_y, validation_y = model_selection.train_test_split(X, Y, random_state=42, stratify=Y, test_size=0.20)

    klass_weights = np.asarray([1025.0/7013.0, 1638.0/7013.0, 2673.0/7013.0, 968.0/7013.0, 709.0/7013.0])
    # Free up X and Y memory
    del X
    del Y
    # del x
    # del y
    print("Total time to split: " + str(timedelta(seconds=int(round(time.time() - time0)))))

    print('train_x: {}'.format(train_x.shape))
    print('validation_x: {}'.format(validation_x.shape))
    print('train_y: {}'.format(train_y.shape))
    print('validation_y: {}'.format(validation_y.shape))
    print('np.bincount(train_y)', np.bincount(train_y.astype(dtype=np.int64)))
    print('np.bincount(validation_y)', np.bincount(validation_y.astype(dtype=np.int64)))

    train_y = (np.arange(FLAGS.num_classes) == train_y[:, None])+0
    validation_y = (np.arange(FLAGS.num_classes) == validation_y[:, None])+0

    # Seed numpy random to generate identical random numbers every time (used in batching)
    np.random.seed(42)

    def get_validation_batch(validation_x_ids, validation_y, batch_number):
        num_images = len(validation_x_ids)

        count = 0
        start_index = batch_number * FLAGS.batch_size
        end_index = start_index + FLAGS.batch_size
        end_index = num_images if end_index > num_images else end_index
        real_batch_size = end_index - start_index

        validation_x = np.ndarray([real_batch_size, FLAGS.chunk_size, FLAGS.chunk_size, FLAGS.chunk_size, 1], dtype=np.float32)

        for chunk_id in validation_x_ids[start_index : end_index]:
            chunk = np.load(DATA_PATH + chunk_id + '_X.npy').astype(np.float32, copy=False)
            validation_x[count, :, :, :, :] = img_to_rgb(chunk)
            count = count + 1

        return validation_x, validation_y[start_index : end_index]

    def feed_dict(is_train, batch_number = 0):
        if is_train:
            x_batch, y_batch = get_batch(train_x, train_y)
            k = FLAGS.keep_prob
        else:
            x_batch, y_batch = get_validation_batch(validation_x, validation_y, batch_number)
            k = 1.0
        crss_entrpy_weights = np.ones((y_batch.shape[0]))
        for m in range(y_batch.shape[0]):
            crss_entrpy_weights[m] = np.amax(y_batch[m] * klass_weights)
        return {x: x_batch, y_labels: y_batch, keep_prob: k, cross_entropy_weights: crss_entrpy_weights}

    # Graph construction
    graph = tf.Graph()
    with graph.as_default():
        x = tf.placeholder(tf.float32, shape=[None, FLAGS.chunk_size, FLAGS.chunk_size, FLAGS.chunk_size, 1], name = 'x')
        y = tf.placeholder(tf.float32, shape=[None, FLAGS.num_classes], name = 'y')
        y_labels = tf.placeholder(tf.float32, shape=[None, FLAGS.num_classes], name ='y_labels')
        cross_entropy_weights = tf.placeholder(tf.float32, shape=[None], name ='cross_entropy_weights')
        keep_prob = tf.placeholder(tf.float32)

        class_weights_base = tf.ones_like(y_labels)
        class_weights = tf.multiply(class_weights_base , [1025.0/7013.0, 1638.0/7013.0, 2673.0/7013.0, 968.0/7013.0, 709.0/7013.0])

        # layer1
        conv1_1_out, conv1_1_weights = conv3d(inputs = x, filter_size = 3, num_filters = 16, num_channels = 1, strides = [1, 3, 3, 3, 1], layer_name ='conv1_1')
        relu1_1_out = relu_3d(inputs = conv1_1_out, layer_name='relu1_1')

        conv1_2_out, conv1_2_weights = conv3d(inputs = relu1_1_out, filter_size = 3, num_filters = 16, num_channels = 16, strides = [1, 3, 3, 3, 1], layer_name ='conv1_2')
        relu1_2_out = relu_3d(inputs = conv1_2_out, layer_name='relu1_2')

        pool1_out = max_pool_3d(inputs = relu1_2_out, filter_size = [1, 2, 2, 2, 1], strides = [1, 2, 2, 2, 1], layer_name ='pool1')

        # layer2
        conv2_1_out, conv2_1_weights = conv3d(inputs = pool1_out, filter_size = 3, num_filters = 32, num_channels = 16, strides = [1, 3, 3, 3, 1], layer_name ='conv2_1')
        relu2_1_out = relu_3d(inputs = conv2_1_out, layer_name='relu2_1')

        conv2_2_out, conv2_2_weights = conv3d(inputs = relu2_1_out, filter_size = 3, num_filters = 32, num_channels = 32, strides = [1, 3, 3, 3, 1], layer_name ='conv2_2')
        relu2_2_out = relu_3d(inputs = conv2_2_out, layer_name='relu2_2')

        pool2_out = max_pool_3d(inputs = relu2_2_out, filter_size = [1, 2, 2, 2, 1], strides = [1, 2, 2, 2, 1], layer_name ='pool2')

        # # layer3
        conv3_1_out, conv3_1_weights = conv3d(inputs = pool2_out, filter_size = 3, num_filters = 64, num_channels = 32, strides = [1, 3, 3, 3, 1], layer_name ='conv3_1')
        relu3_1_out = relu_3d(inputs = conv3_1_out, layer_name='relu3_1')

        conv3_2_out, conv3_2_weights = conv3d(inputs = relu3_1_out, filter_size = 3, num_filters = 64, num_channels = 64, strides = [1, 3, 3, 3, 1], layer_name ='conv3_2')
        relu3_2_out = relu_3d(inputs = conv3_2_out, layer_name='relu3_2')

        conv3_3_out, conv3_3_weights = conv3d(inputs = relu3_2_out, filter_size = 3, num_filters = 64, num_channels = 64, strides = [1, 3, 3, 3, 1], layer_name ='conv3_3')
        relu3_3_out = relu_3d(inputs = conv3_3_out, layer_name='relu3_3')

        pool3_out = max_pool_3d(inputs = relu3_3_out, filter_size = [1, 2, 2, 2, 1], strides = [1, 2, 2, 2, 1], layer_name ='pool3')

        # # layer4
        conv4_1_out, conv4_1_weights = conv3d(inputs = pool3_out, filter_size = 3, num_filters = 128, num_channels = 64, strides = [1, 3, 3, 3, 1], layer_name ='conv4_1')
        relu4_1_out = relu_3d(inputs = conv4_1_out, layer_name='relu4_1')

        conv4_2_out, conv4_2_weights = conv3d(inputs = relu4_1_out, filter_size = 3, num_filters = 128, num_channels = 128, strides = [1, 3, 3, 3, 1], layer_name ='conv4_2')
        relu4_2_out = relu_3d(inputs = conv4_2_out, layer_name='relu4_2')

        conv4_3_out, conv4_3_weights = conv3d(inputs = relu4_2_out, filter_size = 3, num_filters = 128, num_channels = 128, strides = [1, 3, 3, 3, 1], layer_name ='conv4_3')
        relu4_3_out = relu_3d(inputs = conv4_3_out, layer_name='relu4_3')

        pool4_out = max_pool_3d(inputs = relu4_3_out, filter_size = [1, 2, 2, 2, 1], strides = [1, 2, 2, 2, 1], layer_name ='pool4')

        # # layer5
        conv5_1_out, conv5_1_weights = conv3d(inputs = pool4_out, filter_size = 3, num_filters = 256, num_channels = 128, strides = [1, 3, 3, 3, 1], layer_name ='conv5_1')
        relu5_1_out = relu_3d(inputs = conv5_1_out, layer_name='relu5_1')

        conv5_2_out, conv5_2_weights = conv3d(inputs = relu5_1_out, filter_size = 3, num_filters = 256, num_channels = 256, strides = [1, 3, 3, 3, 1], layer_name ='conv5_2')
        relu5_2_out = relu_3d(inputs = conv5_2_out, layer_name='relu5_2')

        conv5_3_out, conv5_3_weights = conv3d(inputs = relu5_2_out, filter_size = 3, num_filters = 256, num_channels = 256, strides = [1, 3, 3, 3, 1], layer_name ='conv5_3')
        relu5_3_out = relu_3d(inputs = conv5_3_out, layer_name='relu5_3')

        pool5_out = max_pool_3d(inputs = relu5_3_out, filter_size = [1, 2, 2, 2, 1], strides = [1, 2, 2, 2, 1], layer_name ='pool5')
        flatten5_out, flatten5_features = flatten_3d(pool5_out, layer_name='flatten5')

        # layer6
        dense6_out = dense_3d(inputs=flatten5_out, num_inputs=int(flatten5_out.shape[1]), num_outputs=4096, layer_name ='fc6')
        relu6_out = relu_3d(inputs = dense6_out, layer_name='relu6')
        dropout6_out = dropout_3d(inputs = relu6_out, keep_prob = keep_prob, layer_name='drop6')

        # layer7
        dense7_out = dense_3d(inputs=dropout6_out, num_inputs=int(dropout6_out.shape[1]), num_outputs=4096, layer_name ='fc7')
        relu7_out = relu_3d(inputs = dense7_out, layer_name='relu7')
        dropout7_out = dropout_3d(inputs = relu7_out, keep_prob = keep_prob, layer_name='drop7')

        # layer8
        dense8_out = dense_3d(inputs=dropout7_out, num_inputs=int(dropout7_out.shape[1]), num_outputs=1000, layer_name ='fc8')

        # layer9
        dense9_out = dense_3d(inputs=dense8_out, num_inputs=int(dense8_out.shape[1]), num_outputs=FLAGS.num_classes, layer_name ='fc9')

        # Final softmax
        y = tf.nn.softmax(dense9_out)

        # Overall Metrics Calculations
        with tf.name_scope('log_loss'):
            log_loss = tf.losses.log_loss(y_labels, y, epsilon=10e-15) #+ tf.add_n(tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES))
            tf.summary.scalar('log_loss', log_loss)

        with tf.name_scope('softmax_cross_entropy'):
            softmax_cross_entropy = tf.losses.softmax_cross_entropy(y_labels, dense9_out) #+ tf.add_n(tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES))
            tf.summary.scalar('softmax_cross_entropy', softmax_cross_entropy)

        with tf.name_scope('accuracy'):
            correct_prediction = tf.equal(tf.argmax(y, 1), tf.argmax(y_labels, 1))
            accuracy = tf.reduce_mean(tf.cast(correct_prediction, "float"))
            tf.summary.scalar('accuracy', accuracy)

        with tf.name_scope('weighted_log_loss'):
            weighted_log_loss = tf.losses.log_loss(y_labels, y, weights=class_weights, epsilon=10e-15) #+ tf.add_n(tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES))
            tf.summary.scalar('weighted_log_loss', weighted_log_loss)

        with tf.name_scope('weighted_softmax_cross_entropy'):
            weighted_softmax_cross_entropy = tf.losses.softmax_cross_entropy(y_labels, dense9_out, weights=cross_entropy_weights)
            tf.summary.scalar('weighted_softmax_cross_entropy', weighted_softmax_cross_entropy)

        with tf.name_scope('sparse_softmax_cross_entropy'):
            y_labels_argmax_int = tf.to_int32(tf.argmax(y_labels, axis=1))
            sparse_softmax_cross_entropy = tf.losses.sparse_softmax_cross_entropy(labels=y_labels_argmax_int, logits=dense9_out) #+ tf.add_n(tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES))
            tf.summary.scalar('sparse_softmax_cross_entropy', sparse_softmax_cross_entropy)

        with tf.name_scope('weighted_sparse_softmax_cross_entropy'):
            y_labels_argmax_int = tf.to_int32(tf.argmax(y_labels, axis=1))
            weighted_sparse_softmax_cross_entropy = tf.losses.sparse_softmax_cross_entropy(labels=y_labels_argmax_int, logits=dense9_out, weights=cross_entropy_weights)
            tf.summary.scalar('weighted_sparse_softmax_cross_entropy', weighted_sparse_softmax_cross_entropy)

        # Class Based Metrics calculations

        y_pred_class = tf.argmax(y, 1)
        y_labels_class = tf.argmax(y_labels, 1)

        confusion_matrix = tf.confusion_matrix(y_labels_class, y_pred_class, num_classes=FLAGS.num_classes)

        sum_row_0 = tf.reduce_sum(confusion_matrix[0, :])
        sum_row_1 = tf.reduce_sum(confusion_matrix[1, :])
        sum_row_2 = tf.reduce_sum(confusion_matrix[2, :])
        sum_row_3 = tf.reduce_sum(confusion_matrix[3, :])
        sum_row_4 = tf.reduce_sum(confusion_matrix[4, :])
        #sum_row_5 = tf.reduce_sum(confusion_matrix[5, :])

        sum_col_0 = tf.reduce_sum(confusion_matrix[:, 0])
        sum_col_1 = tf.reduce_sum(confusion_matrix[:, 1])
        sum_col_2 = tf.reduce_sum(confusion_matrix[:, 2])
        sum_col_3 = tf.reduce_sum(confusion_matrix[:, 3])
        sum_col_4 = tf.reduce_sum(confusion_matrix[:, 4])
        #sum_col_5 = tf.reduce_sum(confusion_matrix[:, 5])

        sum_all = tf.reduce_sum(confusion_matrix[:, :])

        with tf.name_scope('precision'):
            precision_0 = confusion_matrix[0,0] / sum_col_0
            precision_1 = confusion_matrix[1,1] / sum_col_1
            precision_2 = confusion_matrix[2,2] / sum_col_2
            precision_3 = confusion_matrix[3,3] / sum_col_3
            precision_4 = confusion_matrix[4,4] / sum_col_4
            # precision_5 = confusion_matrix[5,5] / sum_col_5

            tf.summary.scalar('precision_0', precision_0)
            tf.summary.scalar('precision_1', precision_1)
            tf.summary.scalar('precision_2', precision_2)
            tf.summary.scalar('precision_3', precision_3)
            tf.summary.scalar('precision_4', precision_4)
            # tf.summary.scalar('precision_5', precision_5)

        with tf.name_scope('recall'):
            recall_0 = confusion_matrix[0,0] / sum_row_0
            recall_1 = confusion_matrix[1,1] / sum_row_1
            recall_2 = confusion_matrix[2,2] / sum_row_2
            recall_3 = confusion_matrix[3,3] / sum_row_3
            recall_4 = confusion_matrix[4,4] / sum_row_4
            # recall_5 = confusion_matrix[5,5] / sum_row_5

            tf.summary.scalar('recall_0', recall_0)
            tf.summary.scalar('recall_1', recall_1)
            tf.summary.scalar('recall_2', recall_2)
            tf.summary.scalar('recall_3', recall_3)
            tf.summary.scalar('recall_4', recall_4)
            # tf.summary.scalar('recall_5', recall_5)

        with tf.name_scope('specificity'):
            tn_0 = sum_all - (sum_row_0 + sum_col_0 - confusion_matrix[0,0])
            fp_0 = sum_col_0 - confusion_matrix[0,0]
            specificity_0 = tn_0 / (tn_0 + fp_0)

            tn_1 = sum_all - (sum_row_1 + sum_col_1 - confusion_matrix[1,1])
            fp_1 = sum_col_1 - confusion_matrix[1,1]
            specificity_1 = tn_1 / (tn_1 + fp_1)

            tn_2 = sum_all - (sum_row_2 + sum_col_2 - confusion_matrix[2,2])
            fp_2 = sum_col_2 - confusion_matrix[2,2]
            specificity_2 = tn_2 / (tn_2 + fp_2)

            tn_3 = sum_all - (sum_row_3 + sum_col_3 - confusion_matrix[3,3])
            fp_3 = sum_col_3 - confusion_matrix[3,3]
            specificity_3 = tn_3 / (tn_3 + fp_3)

            tn_4 = sum_all - (sum_row_4 + sum_col_4 - confusion_matrix[4,4])
            fp_4 = sum_col_4 - confusion_matrix[4,4]
            specificity_4 = tn_4 / (tn_4 + fp_4)

            # tn_5 = sum_all - (sum_row_5 + sum_col_5 - confusion_matrix[5,5])
            # fp_5 = sum_col_5 - confusion_matrix[5,5]
            # specificity_5 = tn_5 / (tn_5 + fp_5)

            tf.summary.scalar('specificity_0', specificity_0)
            tf.summary.scalar('specificity_1', specificity_1)
            tf.summary.scalar('specificity_2', specificity_2)
            tf.summary.scalar('specificity_3', specificity_3)
            tf.summary.scalar('specificity_4', specificity_4)
            # tf.summary.scalar('specificity_5', specificity_5)

        with tf.name_scope('true_positives'):
            tp_0 = confusion_matrix[0,0]
            tp_1 = confusion_matrix[1,1]
            tp_2 = confusion_matrix[2,2]
            tp_3 = confusion_matrix[3,3]
            tp_4 = confusion_matrix[4,4]
            # tp_5 = confusion_matrix[5,5]

            tf.summary.scalar('true_positives_0', tp_0)
            tf.summary.scalar('true_positives_1', tp_1)
            tf.summary.scalar('true_positives_2', tp_2)
            tf.summary.scalar('true_positives_3', tp_3)
            tf.summary.scalar('true_positives_4', tp_4)
            # tf.summary.scalar('true_positives_5', tp_5)

        with tf.name_scope('true_negatives'):
            tf.summary.scalar('true_negatives_0', tn_0)
            tf.summary.scalar('true_negatives_1', tn_1)
            tf.summary.scalar('true_negatives_2', tn_2)
            tf.summary.scalar('true_negatives_3', tn_3)
            tf.summary.scalar('true_negatives_4', tn_4)
            # tf.summary.scalar('true_negatives_5', tn_5)

        with tf.name_scope('false_positives'):
            tf.summary.scalar('false_positives_0', fp_0)
            tf.summary.scalar('false_positives_1', fp_1)
            tf.summary.scalar('false_positives_2', fp_2)
            tf.summary.scalar('false_positives_3', fp_3)
            tf.summary.scalar('false_positives_4', fp_4)
            # tf.summary.scalar('false_positives_5', fp_5)

        with tf.name_scope('false_negatives'):
            fn_0 = sum_row_0 - tp_0
            fn_1 = sum_row_1 - tp_1
            fn_2 = sum_row_2 - tp_2
            fn_3 = sum_row_3 - tp_3
            fn_4 = sum_row_4 - tp_4
            # fn_5 = sum_row_5 - tp_5

            tf.summary.scalar('false_negatives_0', fn_0)
            tf.summary.scalar('false_negatives_1', fn_1)
            tf.summary.scalar('false_negatives_2', fn_2)
            tf.summary.scalar('false_negatives_3', fn_3)
            tf.summary.scalar('false_negatives_4', fn_4)
            # tf.summary.scalar('false_negatives_5', fn_5)

        with tf.name_scope('log_loss_by_class'):
            log_loss_0 = tf.losses.log_loss(y_labels[0], y[0], epsilon=10e-15)
            log_loss_1 = tf.losses.log_loss(y_labels[1], y[1], epsilon=10e-15)
            log_loss_2 = tf.losses.log_loss(y_labels[2], y[2], epsilon=10e-15)
            log_loss_3 = tf.losses.log_loss(y_labels[3], y[3], epsilon=10e-15)
            log_loss_4 = tf.losses.log_loss(y_labels[4], y[4], epsilon=10e-15)
            # log_loss_5 = tf.losses.log_loss(y_labels[5], y[5], epsilon=10e-15)
        
            #added extra '_' to avoid tenosorboard name collision with the main log_loss metric
            tf.summary.scalar('log_loss__0', log_loss_0)
            tf.summary.scalar('log_loss__1', log_loss_1)
            tf.summary.scalar('log_loss__2', log_loss_2)
            tf.summary.scalar('log_loss__3', log_loss_3)
            tf.summary.scalar('log_loss__4', log_loss_4)
            # tf.summary.scalar('log_loss__5', log_loss_5)

        with tf.name_scope('softmax_cross_entropy_by_class'):
            softmax_cross_entropy_0 = tf.losses.softmax_cross_entropy(y_labels[0], dense9_out[0])
            softmax_cross_entropy_1 = tf.losses.softmax_cross_entropy(y_labels[1], dense9_out[1])
            softmax_cross_entropy_2 = tf.losses.softmax_cross_entropy(y_labels[2], dense9_out[2])
            softmax_cross_entropy_3 = tf.losses.softmax_cross_entropy(y_labels[3], dense9_out[3])
            softmax_cross_entropy_4 = tf.losses.softmax_cross_entropy(y_labels[4], dense9_out[4])
            # softmax_cross_entropy_5 = tf.losses.softmax_cross_entropy(y_labels[5], dense9_out[5])
        
            tf.summary.scalar('softmax_cross_entropy_0', softmax_cross_entropy_0)
            tf.summary.scalar('softmax_cross_entropy_1', softmax_cross_entropy_1)
            tf.summary.scalar('softmax_cross_entropy_2', softmax_cross_entropy_2)
            tf.summary.scalar('softmax_cross_entropy_3', softmax_cross_entropy_3)
            tf.summary.scalar('softmax_cross_entropy_4', softmax_cross_entropy_4)
            # tf.summary.scalar('softmax_cross_entropy_5', softmax_cross_entropy_5)

        with tf.name_scope('accuracy_by_class'):
            accuracy_0 = (tp_0 + tn_0)/(tp_0 + fp_0 + fn_0 + tn_0)
            accuracy_1 = (tp_1 + tn_1)/(tp_1 + fp_1 + fn_1 + tn_1)
            accuracy_2 = (tp_2 + tn_2)/(tp_2 + fp_2 + fn_2 + tn_2)
            accuracy_3 = (tp_3 + tn_3)/(tp_3 + fp_3 + fn_3 + tn_3)
            accuracy_4 = (tp_4 + tn_4)/(tp_4 + fp_4 + fn_4 + tn_4)
            # accuracy_5 = (tp_5 + tn_5)/(tp_5 + fp_5 + fn_5 + tn_5)

            tf.summary.scalar('accuracy_0', accuracy_0)
            tf.summary.scalar('accuracy_1', accuracy_1)
            tf.summary.scalar('accuracy_2', accuracy_2)
            tf.summary.scalar('accuracy_3', accuracy_3)
            tf.summary.scalar('accuracy_4', accuracy_4)
            # tf.summary.scalar('accuracy_5', accuracy_5)

        with tf.name_scope('weighted_log_loss_by_class'):
            weighted_log_loss_0 = tf.losses.log_loss(y_labels[0], y[0], weights=class_weights[0], epsilon=10e-15)
            weighted_log_loss_1 = tf.losses.log_loss(y_labels[1], y[1], weights=class_weights[1], epsilon=10e-15)
            weighted_log_loss_2 = tf.losses.log_loss(y_labels[2], y[2], weights=class_weights[2], epsilon=10e-15)
            weighted_log_loss_3 = tf.losses.log_loss(y_labels[3], y[3], weights=class_weights[3], epsilon=10e-15)
            weighted_log_loss_4 = tf.losses.log_loss(y_labels[4], y[4], weights=class_weights[4], epsilon=10e-15)
            # weighted_log_loss_5 = tf.losses.log_loss(y_labels[5], y[5], weights=class_weights[5], epsilon=10e-15)
        
            tf.summary.scalar('weighted_log_loss_0', weighted_log_loss_0)
            tf.summary.scalar('weighted_log_loss_1', weighted_log_loss_1)
            tf.summary.scalar('weighted_log_loss_2', weighted_log_loss_2)
            tf.summary.scalar('weighted_log_loss_3', weighted_log_loss_3)
            tf.summary.scalar('weighted_log_loss_4', weighted_log_loss_4)
            # tf.summary.scalar('weighted_log_loss_5', weighted_log_loss_5)

        with tf.name_scope('f1_score_by_class'):
            f1_score_0 = 2 * (precision_0 * recall_0) / (precision_0 + recall_0)
            f1_score_1 = 2 * (precision_1 * recall_1) / (precision_1 + recall_1)
            f1_score_2 = 2 * (precision_2 * recall_2) / (precision_2 + recall_2)
            f1_score_3 = 2 * (precision_3 * recall_3) / (precision_3 + recall_3)
            f1_score_4 = 2 * (precision_4 * recall_4) / (precision_4 + recall_4)
            # f1_score_5 = 2 * (precision_5 * recall_5) / (precision_5 + recall_5)

            #f1_score = (f1_score_0 * 40591.0/69920.0) + (f1_score_1 * 14624.0/69920.0) + (f1_score_2 * 10490.0/69920.0) + (f1_score_3 *4215.0/ 69920.0)
            tf.summary.scalar('f1_score_0', f1_score_0)
            tf.summary.scalar('f1_score_1', f1_score_1)
            tf.summary.scalar('f1_score_2', f1_score_2)
            tf.summary.scalar('f1_score_3', f1_score_3)
            tf.summary.scalar('f1_score_4', f1_score_4)
            # tf.summary.scalar('f1_score_5', f1_score_5)

        with tf.name_scope('train'):
            optimizer = tf.train.AdamOptimizer(learning_rate=1e-4, name='adam_optimizer').minimize(log_loss)

        merged = tf.summary.merge_all()
        saver = tf.train.Saver()

    # Setting up config
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = FLAGS.allow_growth
    config.log_device_placement=FLAGS.log_device_placement
    config.allow_soft_placement=FLAGS.allow_soft_placement

    # timestamp used to identify the start of run
    start_timestamp = str(int(time.time()))
    model_id = str(uuid.uuid4())

    # Name used to save all artifacts of run
    run_name = 'runType={0:}_timestamp={1:}_batchSize={2:}_maxIterations={3:}_numTrain={4:}_numValidation={5:}_modelId={6:}'
    train_run_name = run_name.format('train', start_timestamp, FLAGS.batch_size, FLAGS.max_iterations,
                               train_x.shape[0], validation_x.shape[0], model_id)

    test_run_name = run_name.format('test', start_timestamp, FLAGS.batch_size, FLAGS.max_iterations,
                               train_x.shape[0], validation_x.shape[0], model_id)

    print('Run_name: {}'.format(train_run_name))

    k_count = 0
    with tf.Session(graph=graph, config=config) as sess:
        train_writer = tf.summary.FileWriter(TENSORBOARD_SUMMARIES + train_run_name, sess.graph)
        test_writer = tf.summary.FileWriter(TENSORBOARD_SUMMARIES + test_run_name, sess.graph)
        sess.run([tf.global_variables_initializer(), tf.local_variables_initializer()])

        for i in tqdm(range(FLAGS.max_iterations)):
            if (i % FLAGS.iteration_analysis == 0) or (i == (FLAGS.max_iterations - 1)):
                save_model(sess, model_id, saver)
                # Validation
                num_batches = int(math.ceil(float(len(validation_x)) / FLAGS.batch_size))
                for k in range(num_batches):
                    _, step_summary = sess.run([y, merged], feed_dict=feed_dict(False, k))
                    test_writer.add_summary(step_summary, k_count)
                    k_count = k_count + 1
            else:
                # Train
                _, step_summary = sess.run([optimizer, merged], feed_dict=feed_dict(True))
                train_writer.add_summary(step_summary, i)

        train_writer.close()
        test_writer.close()
        # Clossing session
        sess.close()

if __name__ == '__main__':
    start_time = time.time()
    DATA_PATH = '/kaggle_2/lidc_idri/data/nodules_nz_aug/'
    TENSORBOARD_SUMMARIES = '/kaggle_2/lidc_idri/tensorboard_summaries/'
    MODELS = '/kaggle_2/lidc_idri/models/'

    #globals initializing
    FLAGS = tf.app.flags.FLAGS

    ## Prediction problem specific
    tf.app.flags.DEFINE_integer('iteration_analysis', 1000,
                                """Number of steps after which analysis code is executed""")
    tf.app.flags.DEFINE_integer('chunk_size', 32,
                                """Size of chunks used.""")
    tf.app.flags.DEFINE_integer('num_classes', 5,
                                """Number of classes to predict.""")
    tf.app.flags.DEFINE_integer('batch_size', 64,
                                """Number of items in a batch.""")
    tf.app.flags.DEFINE_integer('max_iterations', 100000,
                                """Number of batches to run.""")
    tf.app.flags.DEFINE_float('reg_constant', 0.0, 'Regularization constant')
    tf.app.flags.DEFINE_float('keep_prob', 1.0, 'Dropout keep probablity')
    tf.app.flags.DEFINE_float('require_improvement_percentage', 0.20,
                                """Percent of max_iterations after which optimization will be halted if no improvement found""")
    tf.app.flags.DEFINE_float('iteration_analysis_percentage', 0.10,
                                """Percent of max_iterations after which analysis will be done""")

    ## Tensorflow specific
    tf.app.flags.DEFINE_boolean('log_device_placement', False,
                                """Whether to log device placement.""")
    tf.app.flags.DEFINE_boolean('allow_soft_placement', True,
                                """Whether to allow soft placement of calculations by tf.""")
    tf.app.flags.DEFINE_boolean('allow_growth', True,
                                """Whether to allow GPU growth by tf.""")

    #post_process()
    print('process started')
    train_3d_nn()
    end_time = time.time()
    print("Total Time usage: " + str(timedelta(seconds=int(round(end_time - start_time)))))
