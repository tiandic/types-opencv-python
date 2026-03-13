## types-opencv

This is an OpenCV stubs project.

Based on the `pyopencv_signatures.json` generated from building the OpenCV documentation, as well as the XML documentation generated after building, the local Python environment for running this project, and my patch generation.

Because the generated stubs are based on the OpenCV documentation, all classes, functions, function documentation, and constants included in the OpenCV documentation will be included.

The official OpenCV stubs are generated for the new version and do not include functions with `_create` (for example: `cv2.ORB_create`), but these functions still exist in the documentation and can still be used. This project includes these functions.

However, there are still shortcomings, the main one being the type hints for function return values.

This is due to the large number of placeholder types `retval` in the Python sections of the OpenCV documentation.

`patch.json` is my patch for this issue, but since the project is still in its early stages, there may be imperfections. Feedback through [issues](https://github.com/tiandic/types-opencv-python/issues) is welcome to help further improve the project.

---
### Install
#### 1. pypi
```bash
pip install types-opencv-python
# or
pip install types-opencv-contrib-python
```

---
#### 2. Generated based on the local environment

- Required Python dependencies:
```bash
pip install bs4
pip install lxml
pip install pyflakes
pip install opencv-python # opencv-contrib-python
```

- Compile and install Doxygen

```bash
wget https://github.com/doxygen/doxygen/releases/download/Release_1_16_1/doxygen-1.16.1.src.tar.gz
tar -xf doxygen-1.16.1.src.tar.gz
cd doxygen-1.16.1
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

- Generate document
```bash
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git

cd opencv_contrib && git checkout 4.13.0 && cd ..
cd opencv && git checkout 4.13.0 && cd ..

mkdir build && cd build

cmake -DBUILD_DOCS=ON -DOPENCV_EXTRA_MODULES_PATH=../opencv_contrib/modules ../opencv

sed -i 's/^\(\s*GENERATE_XML\s*=\s*\)NO/\1YES/' doc/Doxyfile

make doxygen -j$(nproc)
```

- Generate stubs
```bash
git clone https://github.com/tiandic/types-opencv-python.git
cd types-opencv-python
python3 gen_stubs2.py .. genout # The first parameter is the build directory of the opencv documentation, and the second parameter is the stubs output directory
```

In addition, if you need to generate stubs based on a `cv*.so` at a specified path instead of the cv2 installed in the current Python environment, you can specify the third parameter as the directory where the `cv*.so` is located. For example, if the specified `cv*.so` is `/a/b/c/cv2.abi3.so`, then the third parameter should be `/a/b/c`.

The stubs generated in genout
You can use the following command to install
```bash
cp pyproject.toml genout
cd genout
pip install .
```
`pyproject.toml` is the default configuration for the dependency `opencv-python`. Modify it before installation if necessary.
