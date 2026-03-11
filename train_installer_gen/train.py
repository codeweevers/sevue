import os
import tensorflow as tf
import multiprocessing

assert tf.__version__.startswith("2")
num_threads = multiprocessing.cpu_count()
tf.config.threading.set_inter_op_parallelism_threads(num_threads)
tf.config.threading.set_intra_op_parallelism_threads(num_threads)
from mediapipe_model_maker import gesture_recognizer

print("GPUs:", tf.config.list_physical_devices("GPU"))
import matplotlib.pyplot as plt

data = gesture_recognizer.Dataset.from_folder(
    dirname="frames",
    hparams=gesture_recognizer.HandDataPreprocessingParams(shuffle=True),
)
train_data, rest_data = data.split(0.6)
validation_data, test_data = rest_data.split(0.5)
hparams = gesture_recognizer.HParams(
    export_dir="exported_model",
    epochs=20,  # default is fine
    learning_rate=0.001,  # default is fine
)
options = gesture_recognizer.GestureRecognizerOptions(hparams=hparams)
model = gesture_recognizer.GestureRecognizer.create(
    train_data=train_data, validation_data=validation_data, options=options
)
loss, acc = model.evaluate(test_data, batch_size=64)
print(f"Test loss:{loss}, Test accuracy:{acc}")
model.export_model()
