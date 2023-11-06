import cv2
import cv2.typing
import imutils
import matplotlib.pyplot as plt
import numpy as np

templates: np.ndarray = np.load('./common/templates.npy')

ROI_MIN_WIDTH = 15
CONFIDENCE_THRESHOLD = 0.3
ROI_MIN_HEIGHT = 15
ANNOTATION_COLOR = (200, 0, 200)
ROI_RESCALE_WIDTH, ROI_RESCALE_HEIGHT = templates.shape[1:]


def find_contour(image: str | cv2.typing.MatLike) -> tuple[np.ndarray] | bool:
    """Find contours in image for landing UAV.
    
    Parameters
    ----------
    image : str | cv2.typing.MatLike
        Image or image path.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray]
        contours, processed, original of input image.
    bool
        False if image doesn't load.
    """
    
    if isinstance(image, str):
        image = cv2.imread(image)
        if image is None:
            return False

    image = imutils.resize(image, 1024)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = cv2.GaussianBlur(image, (3, 3), 0)

    processed = cv2.normalize(image, None, 0, 1.0, cv2.NORM_MINMAX, dtype=cv2.CV_32F)

    lowerb = np.min(np.min(processed, axis=0), axis=0)
    upperb = np.max(np.max(processed, axis=0), axis=0)
    upperb[2] *= 0.3
    mask = cv2.inRange(processed, lowerb, upperb)
    
    processed = cv2.bitwise_and(processed, processed, mask=mask)
    processed = cv2.cvtColor(processed, cv2.COLOR_RGB2GRAY)
    processed *= 255
    processed = np.array(processed, np.uint8)

    _, processed = cv2.threshold(processed, 60, 1.0, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # contoured = np.zeros_like(processed)
    # cv2.drawContours(contoured, contours, -1, ANNOTATION_COLOR)
    # plt.figure()
    # plt.imshow(contoured)
    # plt.show()

    return contours, processed, image


def find(image: str | cv2.typing.MatLike, radius: int = 160, display: bool = False, confidence_threshold: float = CONFIDENCE_THRESHOLD) -> tuple | bool:
    """Find 'H' in image for landing UAV.
    
    Parameters
    ----------
    image : str | cv2.typing.MatLike
        Image or image path.
    radius : int
        Mask radius to account for landing light.
    display : bool
        Should I display any found Hs?
    confidence_threshold : float
        Zero to one of required confidence.

    Returns
    -------
    tuple[int, int, float]
        Hx, Hy, Confidence of calculated image.
    bool
        False if nothing exciting happens.
    """

    if out := find_contour(image):
        contours, processed, image = out
    else:
        return False
    confidences = np.zeros((len(contours)))

    for n, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        # roi: np.ndarray = processed[y:y+h, x:x+w]

        roi = np.zeros_like(processed)
        cv2.drawContours(roi, contours, n, (1.0), thickness=cv2.FILLED)
        roi: np.ndarray = roi[y:y+h, x:x+w]

        if roi.shape[0] < ROI_MIN_WIDTH or roi.shape[1] < ROI_MIN_HEIGHT:
            continue

        ratio = roi.shape[0]/roi.shape[1]
        if not (1/3 < ratio < 3/1):
            continue

        roi = cv2.resize(roi, (ROI_RESCALE_WIDTH, ROI_RESCALE_HEIGHT))

        strength = np.zeros((templates.shape[0]))

        for i, template in enumerate(templates):
            invtemplate = 1 - template

            posmatch = np.multiply(template, roi)
            invmatch = np.multiply(invtemplate, roi)

            match = posmatch - invmatch

            strength[i] = (np.sum(match)) / np.sum(template)

            # print( "----------------")
            # print(f"Template: {np.sum(template)}")
            # print(f"InverseT: {np.sum(invtemplate)}")
            # print(f"PosMatch: {np.sum(posmatch)}")
            # print(f"InvMatch: {np.sum(invmatch)}")
            # print(f"Strength: {strength[i]}")
            # plt.figure()
            # plt.imshow(match)
            # plt.show()

        confidences[n] = np.max(strength)

    if confidences.size <= 0:
        return False
    
    confidence = np.max(confidences)

    if confidence <= 0.0:
        return False

    # if confidence < confidence_threshold:
    #     return False

    index = np.where(confidences==np.max(confidences))[0][0]
    x, y, w, h = cv2.boundingRect(contours[index])
    yc = image.shape[0]//2 - (y + h//2)
    xc = (x + w//2) - image.shape[1]//2

    if display:
        plt.figure()
        cv2.rectangle(image, (x, y), (x+w, y+h), color=ANNOTATION_COLOR, thickness=2)
        cv2.circle(image, (x + w//2, y + h//2), radius=2, color=ANNOTATION_COLOR, thickness=-1)
        plt.imshow(image)
        plt.show()
        
    return xc, yc, confidence


def _test(file):
    if out:=find(file, display=True):
        x_offset, y_offset, confidence = out
        print(f"'H' detected in {file} at ({x_offset},{y_offset}) with a confidence of {confidence:.2f}.")
    else:
        print(f"None detected in {file}.")


if __name__ == '__main__':
    # for i in range(1,10):
    #     _test(f'./stored_images/image{i}.png')

    _test('./stored_images/Cessna_172SP - 2023-11-05 10.56.34.png')