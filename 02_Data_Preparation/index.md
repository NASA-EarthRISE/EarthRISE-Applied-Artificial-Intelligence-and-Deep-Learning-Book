# 2\. Data Preparation

**Tim Mayer** <a href="https://orcid.org/0000-0001-9489-9392"><img src="https://orcid.org/sites/default/files/images/orcid_16x16.png" style="vertical-align:middle"/></a> · NASA - EarthRISE · University of Alabama in Huntsville<br>
**Biplov Bhandari** <a href="https://orcid.org/0000-0001-6169-8236"><img src="https://orcid.org/sites/default/files/images/orcid_16x16.png" style="vertical-align:middle"/></a> · Earth Resources Technology<br>

Data Preparation is vital for the success of any Artificial Intelligence or Machine Learning project. Every chapter, workflow, and use case in this book is enabled through decisions made before model training ever begins. The authors have applied their expertise when selecting the preferred sensor, bands, and inputs to address the phenomenon at hand; what spatial or timeseries information contextualizes the problem; how to efficiently scale and normalize values; how data is split and partitioned, to stage and store data for computationally efficient training. The section provides a snapshot across the current chapters to demonstrate the various dimensions required for effective data preparation. This section groups those data preparation choices by problem area, and distills them into practices the reader can adopt and reuse. Going forward, find the chapter closest to your problem, see how its data was shaped, then adapt that approach to your own challenge. Finally, there are a wide array of resources ranging from basic to exhaustive available effectively prepping geospatial data. Please refer to those for further context, this short section is to familiarize you with the workflows available in the book and get the reader started in the hands-on section as fast as possible. 

| Chapter | Task | Sensor / resolution | Model input | Normalization | Partition | Storage / hosting |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| [3.1 Rice Mapping](../03_Semantic_Segmentation/01__Crop_Mapping/notebooks/Rice_Mapping_Bhutan_2021.ipynb) | Multi-class segmentation | PlanetScope NICFI, exported at 10 m; optional DEM, Sentinel-1 | 256×256 patches (U-Net), 1×1 points (DNN); 8 bands (RGBN pre-season \+ growing season) | Float reflectance composites; no indices | \~70/20/10 by sample point; independent CEO points | GZIP TFRecords on Google Cloud Storage |
| [3.2 Selective Logging](../03_Semantic_Segmentation/02__Selective_Logging_Detection/notebooks/Selective_Logging_Detection.ipynb) | Binary segmentation | SkySat 0.5 m, 4 bands | 128×128 patches | Raw values; BatchNorm in network | 70/20/10 by polygon, seeded | TFRecords on Drive \+ Zenodo DOI; COG for inference |
| [3.3 Clay Deforestation](../03_Semantic_Segmentation/03__Clay_Deforestation_Segmentation_Model/notebooks/ClayDeforestationv3.ipynb) | Binary change segmentation | Sentinel-2, 10 bands, 10 m | 512×512 before/after/label chips | Per-band z-score with Clay statistics; wavelength \+ GSD metadata | Separate train (50) / val (20) sets | GeoTIFF chips on Drive |
| [5.1 Soybean Yield](../05_Time_Series/01__Soybean_Yield_Prediction/notebooks/Crop_yield_estimationR4.ipynb) | Regression with uncertainty | EVI2, LST, climate, soil moisture; county level | 6 phenological stages × 14 features | Z-score from training data only | Train/test, 80/20 train/val; per-year evaluation | NPY arrays via GitHub Release |
| [6.1 Active Fire BNN](../06_Eco_Process_Sim/01__Active_Fire_Detection/notebooks/BNN_Active_Fire_Detection.ipynb) | Binary classification with uncertainty | VIIRS and MODIS hotspot attributes | Tabular features per detection | BatchNorm as first layer | 80/20, plus 20% validation | CSV |
| [10.1 Evaluating EOFMs](../10_Future/01__Evaluating_Foundation_Models_Trained_with_Earth_Observation_Data/notebooks/Chapter_Practical_EOFM_Evaluation.ipynb) | Embeddings \+ classifier | HLS, 6 bands, 30 m | 256×256 chips; 4-date sequences (Prithvi) | Clay statistics; encoded date and location | Manual split of 22 images | Streamed from NASA STAC |
| [10.2 EOFM Benchmarking](../10_Future/02__Comprehensive_EOFM_Benchmarking/notebooks/Chapter_Comprehensive_EOFM_Benchmarking.ipynb) | Segmentation benchmark | HLS Burn Scars, MTBS | Benchmark tiles | Framework preprocessing configs | Fixed benchmark splits | Hugging Face, Drive |

## 

## 2.2 Preparation by Problem Area

### Semantic segmentation (Chapters 3.1, 3.2, 3.3)

All three chapters follow the same pattern: **turn labels into a raster band aligned with the imagery, cut fixed-size patches, store them in a format built for streaming into a model, and stitch predictions back into a georeferenced map.**

- **Labels as a band.** Polygons are rasterized onto the same grid as the image (Chapter 3.2 stores the label as a byte band to save space). Misalignment between image and label is the most common silent failure in segmentation.  
- **Patch size follows the object.** Logging roads fit in 128×128 at 0.5 m (64 m across). Rice terraces need landscape context, so Chapter 3.1 uses 256×256 at 10 m (2.56 km). Chapter 3.3 uses 512×512 at 10 m to capture clearing patterns.  
- **Patch versus point.** Chapter 3.1 exports the same sample locations twice: patches for U-Net and single pixels for a DNN. The model type determines the data structure, so choose the model before exporting.  
- **Inference mirrors training.** Chapter 3.2 pads the scene, cuts it into patches, predicts, and stitches the results, and notes the grid artifacts this creates. Overlapping patches with blended edges remove them.

The value of this approach is that patches give the model spatial context, a fixed format makes training fast and repeatable, and storing data in the cloud lets anyone rerun the chapter.

The three chapters scale their inputs differently, and the contrast is the lesson. Chapter 3.1 uses reflectance values. Chapter 3.2 feeds raw values and lets normalization layers inside the network do the work. Chapter 3.3 must standardize with Clay's published statistics because a pretrained model expects inputs on the scale it learned from. **Training from scratch gives you freedom; a pretrained model removes it.**

### Time series and tabular data (Chapters 5.1, 6.1)

These chapters prepare features rather than images, so the work shifts to aggregation, scaling, and balance.

- **Align time to biology, not the calendar.** Chapter 5.1 groups its predictors into six crop growth stages rather than fixed weeks, so each timestep means the same thing in every county and year.  
- **Scale with training statistics only.** Chapter 5.1 computes means and standard deviations on the training set and applies them unchanged to every test year.  
- **Balance deliberately.** Chapter 6.1 balances true and false fire detections and also balances between satellites, so the model learns fire signatures instead of sensor quirks. Chapter 3.3 handles imbalance differently, by giving the rare deforestation class more weight in the loss.

### Foundation models (Chapters 3.3, 10.1, 10.2)

With foundation models, data preparation means **matching what the model was trained on**: the same bands, band order, units, statistics, and resolution.

- Clay accepts any band combination, but each band must come with its central wavelength and normalization statistics, plus the pixel size, date, and location.  
- Prithvi expects six HLS bands as four-date sequences. Apply its published band statistics before use.  
- Chapter 10.2 shows why benchmarks lock splits and preprocessing: comparing models is only fair under identical data conditions.

## 2.3 Normalization Norms

| Method | What it does | When to use |
| :---- | :---- | :---- |
| Fixed scale factor | Divide by a constant (e.g., 10,000 for reflectance) | Known sensor scaling |
| Per-band z-score | Subtract mean, divide by standard deviation | Default for most deep learning; required for pretrained models |
| Percentile clip \+ rescale | Clip extremes, rescale to 0–1 | Data with bright outliers (clouds, fire, urban) |
| In-network normalization | Normalization layer inside the model | Tabular data; statistics travel with the model |

Rules that hold regardless of method:

1. **Compute statistics on the training data only**, then apply them unchanged to validation, test, and new imagery.  
2. **Save the statistics with the model.** Without them, nobody can prepare new inputs correctly.  
3. **Mask clouds and nodata first.** Fill values of 0 distort the statistics.  
4. **Respect units.** Convert radar backscatter to decibels and apply sensor scale factors before standardizing.  
5. **For pretrained models, use the model's statistics**, not your own.

## 2.4 Data Partitioning

The chapters use 70/20/10 (3.1, 3.2), 80/20 (5.1, 6.1), and a fixed train/validation pair (3.3). The ratio matters less than **what you split on**.

- **Split on independent units, not pixels.** Neighboring pixels and overlapping patches are nearly duplicates. If they land in both training and test sets, accuracy is inflated. Chapter 3.2 splits by polygon, so no feature appears in two sets. Spatial blocks work the same way.  
- **Hold out time when predicting the future.** Chapter 5.1 evaluates by year. For forecasting, train on earlier years and test on later ones.  
- **Keep an independent test set.** Chapter 3.1 checks its final map against reference points collected separately in Collect Earth Online, the strongest evidence a model generalizes.  
- **Make splits reproducible.** Use a fixed random seed and save the list of samples in each set.  
- **Keep every class in every set.** Chapter 10.1 assigns its few images by hand to ensure this; stratified sampling does it at scale.

## 2.5 Sensor-Specific Choices

Choose the sensor for the phenomenon, then let the sensor shape the preparation.

- **Object size sets resolution.** Selective logging is small and under the canopy, so Chapter 3.2 needs 0.5 m imagery. Forest clearing is visible at 10 m, so Chapter 3.3 uses free Sentinel-2 data.  
- **Cloud cover sets the source.** Chapter 3.1 uses Planet monthly mosaics because clouds persist over Paro, and compares pre-season with growing-season composites to separate rice from forest.  
- **Harmonized products simplify multi-sensor work.** HLS (Chapters 10.1, 10.2) combines Landsat and Sentinel-2 into one consistent 30 m record.  
- **The sensor itself can be a bias.** Chapter 6.1 shows that prediction uncertainty differs by satellite.  
- **Extra layers are optional.** Chapter 3.1 can add elevation, slope, and radar with a setting. Add them when they carry information the optical bands lack.  
- **Resample carefully.** Use nearest-neighbor for labels and classes so no new values are invented.

## 2.6 To Index or Not to Index

Spectral indices such as NDVI, EVI, and NDWI are central to classical remote sensing and to models like Random Forest. For Deep Learning they are often unnecessary.

**Evidence from this book.** In the study behind Chapter 3.1, a U-Net using four bands plus eight indices reached an F1 score of 85.21% on test data, compared with 84.44% using the four bands alone. The indices were dropped: the gain was small, and fewer inputs meant faster training and prediction. Deep networks learn band combinations, including ratios like NDVI, directly from the raw bands.

**Indices are worth adding when:**

- the model is small and the features are summarized or tabular (Chapter 5.1 uses one index, EVI2);  
- training data is scarce and a known physical signal helps the model learn;  
- results must connect to an established index-based product.

**Leave them out when:**

- you train a convolutional or transformer model on full patches with enough labels;  
- you use a foundation model, which expects only the bands it was trained on;  
- storage or memory is limited, since every extra band adds a full layer to each patch.

**The curse of dimensionality.** Each added feature increases the amount of data needed to learn reliably. Indices built from the same few bands are highly correlated, so they add little new information but do add noise and overfitting risk. Before adding a feature, ask whether it tells the model something the existing bands do not, and test it with and without, as Chapter 3.1 did.

## 2.7 Storage, Formats, and Hosting

| Format | Strength |
| :---- | :---- |
| TFRecord | Streams quickly into TensorFlow; compact |
| GeoTIFF / Cloud-Optimized GeoTIFF (COG) | Keeps location information; COGs allow partial reads over the web |
| NPY | Simple arrays already in model shape |
| CSV | Readable tabular data |
| STAC catalog | Search and stream only the imagery needed |

**Why COGs matter.** A Cloud-Optimized GeoTIFF is a standard GeoTIFF organized into tiles with built-in lower-resolution previews, so software can read just the area it needs over the internet. Chapter 10.1 streams small chips of HLS imagery without downloading whole scenes. Use COGs for anything you will share, serve as a map layer, or read in pieces.

**Hosting.** The chapters use Google Cloud Storage (3.1), Google Drive (3.2, 3.3), Zenodo (3.2), GitHub Releases (5.1), and Hugging Face (10.2). Also leveraging ZARR via Icechunk or Xarrays on local/HPC cluster, on a cloud drive, or cloud buckets are also recommended. Zenodo and Hugging Face suit finished training sets that should be versioned and citable.

**Good habits:** store imagery as 32-bit floats or scaled integers and labels as 8-bit integers; record the bands, dates, and scaling used for every export; and give published training data a DOI.

## 2.8 From This Book to Your Challenge

* **Define what you predict.** A pixel class, an object, a county value, or a single detection decides between patches, points, and tables.  
* **Match the sensor to the phenomenon.** Resolution must resolve the object, revisit must catch the event, and cloud cover must allow observation.  
* **Start from the closest chapter.** i.e. Segmentation: 3.1–3.3. Tabular or seasonal data: 5.1, 6.1. Few labels or new regions: 3.3, 10.1, 10.2.  
* **Start with core bands.** Add indices or extra layers only if a test shows they help.  
* **Size patches to the object plus its surroundings.**  
* **Split on independent units** such as polygons, spatial blocks, or years, and keep a separate test set.  
* **Normalize with training statistics, or the pretrained model's statistics**, and save them.  
* **Check balance** across classes and sensors.  
* **Store in a streaming format**, version it, and host it where others can find and cite it.  
* **For Inference prepare new imagery exactly as you prepared training data.**