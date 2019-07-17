import math
import time
from collections import defaultdict, deque
import numpy as np
import cv2
import os
from requests import get

import config
import object_detection

ip = get('https://api.ipify.org').text

OBJECTS = config.LABELS
STATES = ["start", "wheel-stage", "wheel-compare"]
resources = os.path.abspath("resources/images")
video_url = "http://" + ip + ":9095/"
stable_threshold = 20
wheel_compare_threshold = 15


class FrameRecorder:
    def __init__(self, size):
        self.deque = deque()
        self.size = size
        self.clear_count = 0

    def add(self, obj):
        self.deque.append(obj)

        if len(self.deque) > self.size:
            self.deque.popleft()

        self.clear_count = 0

    def is_center_stable(self):
        if len(self.deque) != self.size:
            return False

        prev_frame = self.deque[0]
        for i in range(1, len(self.deque)):
            frame = self.deque[i]
            diff = bbox_diff(frame["dimensions"], prev_frame["dimensions"])

            if diff > stable_threshold:
                return False

            prev_frame = frame

        return True

    def add_and_check_stable(self, obj):
        self.add(obj)
        return self.is_center_stable()

    def staged_clear(self):
        self.clear_count += 1
        if self.clear_count > self.size:
            self.clear()

    def clear(self):
        self.deque = deque()

    def averaged_bbox(self):
        out = [0, 0, 0, 0]

        for i in range(len(self.deque)):
            dim = self.deque[i]["dimensions"]
            for u in range(len(dim)):
                out[u] += dim[u]

        return [v / len(self.deque) for v in out]

    def averaged_class(self):
        all_class = []
        for i in range(len(self.deque)):
            if self.deque[i]["class_name"] not in all_class:
                all_class.append(self.deque[i]["class_name"])
        return max(set(all_class), key = all_class.count) 


class Task:
    def __init__(self, init_state=None):
        if init_state is None:
            self.current_state = "start"
        else:
            if init_state not in STATES:
                raise ValueError('Unknown init state: {}'.format(init_state))
            self.current_state = init_state

        self.frame_recs = defaultdict(lambda: FrameRecorder(5))
        self.last_id = None
        self.wait_count = 0
        self.history = defaultdict(lambda: False)
        self.delay_flag = False

        self.detector = object_detection.Detector()
        self.frame_count = 0

    def get_objects_by_categories(self, img, categories):
        return self.detector.detect_object(img, categories, self.frame_count)

    def get_instruction(self, img, header=None):
        if header is not None and "task_id" in header:
            if self.last_id is None:
                self.last_id = header["task_id"]
            elif self.last_id != header["task_id"]:
                self.last_id = header["task_id"]
                self.current_state = "start"
                self.history.clear()

        if self.delay_flag is True:
            time.sleep(5)
            self.delay_flag = False

        result = defaultdict(lambda: None)
        result['status'] = "success"
        self.frame_count += 1

        inter = defaultdict(lambda: None)

        # the start, branch into desired instruction
        if self.current_state == "start":
            # self.current_state = "layout_wheels_rims_1"
            self.current_state = "insert_green_washer_1"
        elif self.current_state == "layout_wheels_rims_1":
            inter = self.layout_wheels_rims(img, 1)
            if inter["next"] is True:
                self.current_state = "combine_wheel_rim_1"
        elif self.current_state == "combine_wheel_rim_1":
            inter = self.combine_wheel_rim(1)
            if inter["next"] is True:
                self.current_state = "layout_wheels_rims_2"
        elif self.current_state == "layout_wheels_rims_2":
            inter = self.layout_wheels_rims(img, 2)
            if inter["next"] is True:
                self.current_state = "combine_wheel_rim_2"
        elif self.current_state == "combine_wheel_rim_2":
            inter = self.combine_wheel_rim(2)
            if inter["next"] is True:
                self.current_state = "axle_into_wheel_1"
        elif self.current_state == "axle_into_wheel_1":
            inter = self.axle_into_wheel(img, 1)
            if inter["next"] is True:
                self.current_state = "acquire_black_frame"
        elif self.current_state == "acquire_black_frame":
            inter = self.acquire_black_frame(img)
            if inter["next"] is True:
                self.current_state = "insert_green_washer_1"
        elif self.current_state == "insert_green_washer_1":
            inter = self.insert_green_washer(img, 1)
            if inter["next"] is True:
                self.current_state = "insert_gold_washer"
        elif self.current_state == "insert_gold_washer":
            inter = self.insert_gold_washer(img, 1)
            if inter["next"] is True:
                self.current_state = "insert_pink_gear_front"
        elif self.current_state == "insert_pink_gear_front":
            inter = self.insert_pink_gear_front(img)
            if inter["next"] is True:
                self.current_state = "insert_axle"
        elif self.current_state == "insert_axle":
            inter = self.insert_axle(img, 1)
            if inter["next"] is True:
                self.current_state = "insert_green_washer_2"
        elif self.current_state == "insert_green_washer_2":
            inter = self.insert_green_washer(img, 2)
            if inter["next"] is True:
                self.current_state = "insert_gold_washer_2"
        elif self.current_state == "insert_gold_washer_2":
            inter = self.insert_gold_washer(img, 2)
            if inter["next"] is True:
                self.current_state = "press_wheel_1"
        elif self.current_state == "press_wheel_1":
            inter = self.press_wheel(img, 1)
            if inter["next"] is True:
                self.current_state = "insert_green_washer_3"
        elif self.current_state == "insert_green_washer_3":
            inter = self.insert_green_washer(img, 3)
            if inter["next"] is True:
                self.current_state = "insert_gold_washer_3"
        elif self.current_state == "insert_gold_washer_3":
            inter = self.insert_gold_washer(img, 3)
            if inter["next"] is True:
                self.current_state = "insert_brown_gear"
        elif self.current_state == "insert_brown_gear":
            inter = self.insert_brown_gear(img)
            if inter["next"] is True:
                self.current_state = "insert_pink_gear_back"
        elif self.current_state == "insert_pink_gear_back":
            inter = self.insert_pink_gear_back(img)
            if inter["next"] is True:
                self.current_state = "insert_axle_2"
        elif self.current_state == "insert_axle_2":
            inter = self.insert_axle(img, 2)
            if inter["next"] is True:
                self.current_state = "insert_green_washer_4"
        elif self.current_state == "insert_green_washer_4":
            inter = self.insert_green_washer(img, 4)
            if inter["next"] is True:
                self.current_state = "insert_gold_washer_4"
        elif self.current_state == "insert_gold_washer_4":
            inter = self.insert_gold_washer(img, 4)
            if inter["next"] is True:
                self.current_state = "press_wheel_2"
        elif self.current_state == "press_wheel_2":
            inter = self.press_wheel(img, 2)
            if inter["next"] is True:
                self.current_state = "add_gear_axle"
        elif self.current_state == "add_gear_axle":
            inter = self.add_gear_axle(img)
            if inter["next"] is True:
                self.current_state = "final_check"
        elif self.current_state == "final_check":
            inter = self.final_check(img)
            if inter["next"] is True:
                self.current_state = "complete"
        elif self.current_state == "complete":
            inter = self.complete()
            if inter["next"] is True:
                self.current_state = "nothing"
        elif self.current_state == "nothing":
            self.history = defaultdict(lambda: False)
            time.sleep(10)
            self.current_state = "start"

        for field in inter.keys():
            if field != "next":
                result[field] = inter[field]

        return self.detector.all_detected_objects(), result

    def layout_wheels_rims(self, img, part_id):
        out = defaultdict(lambda: None)
        if self.history["layout_wheels_rims_%s" % part_id] is False:
            self.clear_states()
            self.history["layout_wheels_rims_%s" % part_id] = True
            out['image'] = read_image('tire-rim-legend.jpg')
            speech = {
                1: 'Please find two different sized rims,two different sized tires, and arrange them like this.',
                2: 'Find the other set of two different sized rims, two different sized tires, and show me this configuration.'
            }
            out['speech'] = speech[part_id]
            return out
        
        tires = self.get_objects_by_categories(img, {"thick_wheel_side", "thin_wheel_side"})
        rims = self.get_objects_by_categories(img, {"thick_rim_side", "thin_rim_side"})

        if len(tires) == 2 and len(rims) == 2:
            left_tire, right_tire = separate_two(tires)
            left_rim, right_rim = separate_two(rims)
            if self.frame_recs[0].add_and_check_stable(left_tire) and self.frame_recs[1].add_and_check_stable(right_tire) and self.frame_recs[2].add_and_check_stable(left_rim) and self.frame_recs[3].add_and_check_stable(right_rim): 
                if self.frame_recs[0].averaged_bbox()[1] > self.frame_recs[2].averaged_bbox()[1] and self.frame_recs[1].averaged_bbox()[1] > self.frame_recs[3].averaged_bbox()[1]:
                    rim_diff = compare(self.frame_recs[2].averaged_bbox(),self.frame_recs[3].averaged_bbox(),wheel_compare_threshold)

                    if self.frame_recs[0].averaged_class() == "thick_wheel_side" and self.frame_recs[1].averaged_class() == "thin_wheel_side" and self.frame_recs[2].averaged_class() == "thick_rim_side" and self.frame_recs[3].averaged_class() == "thin_rim_side":
                        out['next'] = True
                    elif self.frame_recs[0].averaged_class() != "thick_wheel_side":
                        out["speech"] = "Please switch out the left tire with a bigger tire."
                    elif self.frame_recs[1].averaged_class() != "thin_wheel_side":
                        out["speech"] = "Please switch out the right tire with a smaller tire."
                    elif rim_diff == "second":
                        out["speech"] = "Please switch the positions of the rims."
                    elif rim_diff == "same":
                        # out["speech"] = "Please switch one of the rims with a different sized one."
                        if self.frame_recs[2].averaged_class() != "thick_rim_side":
                            out["speech"] = "Please switch out the left rim with a bigger rim."
                        elif self.frame_recs[3].averaged_class() != "thin_rim_side":
                            out["speech"] = "Please switch out the right rim with a smaller rim."

                elif self.frame_recs[0].averaged_bbox()[1] > self.frame_recs[2].averaged_bbox()[1] and self.frame_recs[1].averaged_bbox()[1] < self.frame_recs[3].averaged_bbox()[1]:
                    out['speech'] = "The orientation of tire and rim on the right is wrong. Please switch their positions"
                elif self.frame_recs[0].averaged_bbox()[1] < self.frame_recs[2].averaged_bbox()[1] and self.frame_recs[1].averaged_bbox()[1] > self.frame_recs[3].averaged_bbox()[1]:
                    out["speech"] = "The orientation of tire and rim on the left is wrong. Please switch their positions"
                else:
                    out["speech"] = "The orientation of tire and rim on the left and the right is wrong. Please switch the positions of the tire and rim on the left and then switch the positions of the tire and rim on the right."
                self.clear_states()
        else:
            self.all_staged_clear()

        return out

    def combine_wheel_rim(self, part_id):
        out = defaultdict(lambda: None)
        if self.history["combine_wheel_rim_%s" % part_id] is False:
            self.history["combine_wheel_rim_%s" % part_id] = True
            out["speech"] = "Well done. Now assemble the tires and rims as shown in the video."
            out["video"] = video_url + "tire-rim-combine.mp4"
        else:
            out["next"] = True
            time.sleep(10)
        return out

    def axle_into_wheel(self, img, part_id):
        out = defaultdict(lambda: None)
        good_str = "thin" if part_id == 1 else "thick"
        bad_str = "thick" if part_id == 1 else "thin"
        
        if self.history["axle_into_wheel_%s" % part_id] is False:
            self.clear_states()
            self.history["axle_into_wheel_%s" % part_id] = True
            out["image"] = read_image("wheel_in_axle_%s.jpg" % good_str)
            out["speech"] = "Great! Please insert the axle into one of the %s wheels. Then hold it up like this." % good_str
            return out

        good = self.get_objects_by_categories(img, {"wheel_in_axle_%s" % good_str})
        bad = self.get_objects_by_categories(img, {"wheel_in_axle_%s" % bad_str})

        if len(good) != 1 and len(bad) != 1:
            self.all_staged_clear()
            return out

        if len(good) == 1:
            thick_check = self.frame_recs[0].add_and_check_stable(good[0])
            if thick_check is True:
                out["speech"] = "You have the %s wheel. Please use the %s wheel instead" % (good_str, bad_str)
                self.delay_flag = True
                self.clear_states()
        else:
            self.frame_recs[0].staged_clear()

        if len(bad) == 1:
            thin_check = self.frame_recs[1].add_and_check_stable(bad[0])
            if thin_check is True:
                out["next"] = True
        else:
            self.frame_recs[1].staged_clear()

        return out

    def acquire_black_frame(self, img):
        out = defaultdict(lambda: None)
        if self.history["acquire_black_frame"] is False:
            self.clear_states()
            self.history["acquire_black_frame"] = True
            out["speech"] = "Put the axle down and grab the black frame. Show it to me like this."
            out['video'] = video_url + "get_frame.mp4"
            return out

        frame_marker = self.get_objects_by_categories(img, {"frame_marker_right", "frame_marker_left"})
        horn = self.get_objects_by_categories(img, {"frame_horn"})

        if len(frame_marker) != 1 and len(horn) != 1:
            self.all_staged_clear()
            return out

        marker_check = False
        if len(frame_marker) == 1:
            if self.frame_recs[0].add_and_check_stable(frame_marker[0]):
                marker_check = True

        horn_check = False
        if len(horn) == 1:
            if self.frame_recs[1].add_and_check_stable(horn[0]):
                horn_check = True

        if marker_check is True and horn_check is True:
            out["next"] = True

        return out

    def insert_green_washer(self, img, part_id):
        out = defaultdict(lambda: None)
        if self.history["insert_green_washer_%s" % part_id] is False:
            self.clear_states()
            self.history["insert_green_washer_%s" % part_id] = True
            out["speech"] = "Insert the green washer into the left hole."
            out["video"] = video_url + "green_washer_%s.mp4" % part_id
            return out

        holes = self.get_objects_by_categories(img, {"hole_empty", "hole_green"})

        if len(holes) == 2:
            left, right = separate_two(holes)
            good = left if part_id == 1 or part_id == 2 else right

            if good["class_name"] == "hole_green":
                if self.frame_recs[0].add_and_check_stable(good):
                    out["next"] = True
            else:
                self.frame_recs[0].staged_clear()
        else:
            self.frame_recs[0].staged_clear()

        return out

    def insert_gold_washer(self, img, part_id):
        out = defaultdict(lambda: None)
        if self.history["insert_gold_washer_%s" % part_id] is False:
            self.clear_states()
            self.history["insert_gold_washer_%s" % part_id] = True
            out["speech"] = "Great, now insert the gold washer into the green washer."
            out["video"] = video_url + "gold_washer_%s.mp4" % part_id
            return out

        holes = self.get_objects_by_categories(img, {"hole_empty", "hole_green", "hole_gold"})

        if len(holes) == 2:
            left, right = separate_two(holes)
            good = left if part_id == 1 or part_id == 2 else right

            if good["class_name"] == "hole_gold":
                if self.frame_recs[0].add_and_check_stable(good):
                    out["next"] = True
            else:
                self.frame_recs[0].staged_clear()
        else:
            self.frame_recs[0].staged_clear()

        return out

    def insert_pink_gear_front(self, img):
        out = defaultdict(lambda: None)
        if self.history["insert_pink_gear_front"] is False:
            self.clear_states()
            self.history["insert_pink_gear_front"] = True
            out['speech'] = "Lay the black frame down. Now place a pink gear as shown."
            out['video'] = video_url + "pink_gear_1.mp4"
            return out

        bad_pink = self.get_objects_by_categories(img, {"front_gear_bad"})
        if len(bad_pink) >= 1:
            out["speech"] = "Please flip the pink gear around."
            self.frame_recs[0].clear()
            self.delay_flag = True
            return out

        good_pink = self.get_objects_by_categories(img, {"front_gear_good"})
        if len(good_pink) == 1:
            if self.frame_recs[0].add_and_check_stable(good_pink[0]) is True:
                out["next"] = True
        else:
            self.frame_recs[0].staged_clear()

        return out

    def insert_axle(self, img, part_id):
        out = defaultdict(lambda: None)
        if self.history["insert_axle_%s" % part_id] is False:
            self.clear_states()
            self.history["insert_axle_%s" % part_id] = True
            out["speech"] = "Great, now insert the axle through the washers and the pink gear."
            out["video"] = video_url + "axle_into_frame_%s.mp4" % part_id
            return out

        axles = self.get_objects_by_categories(img, {"wheel_axle"})

        good_str = "thin" if part_id == 1 else "thick"
        bad_str = "thick" if part_id == 1 else "thin"

        good = self.get_objects_by_categories(img, {"wheel_in_axle_%s" % good_str})
        bad = self.get_objects_by_categories(img, {"wheel_in_axle_%s" % bad_str})

        if len(bad) == 1:
            thick_check = self.frame_recs[0].add_and_check_stable(bad[0])
            if thick_check is True:
                out["speech"] = "You have the %s wheel. Please use the %s wheel instead." % (bad_str, good_str)
                self.delay_flag = True
                self.clear_states()
        else:
            self.all_staged_clear()

        if len(good) == 1 and len(axles) == 1:
            good_check = self.frame_recs[1].add_and_check_stable(good[0])
            axle_check = self.frame_recs[2].add_and_check_stable(axles[0])
            if good_check and axle_check:
                out["next"] = True
        else:
            self.all_staged_clear()

        return out

    def press_wheel(self, img, part_id):
        out = defaultdict(lambda: None)
        good_str = "thin" if part_id == 1 else "thick"
        bad_str = "thick" if part_id == 1 else "thin"

        if self.history["press_wheel_%s" % part_id] is False:
            self.clear_states()
            self.history["press_wheel_%s" % part_id] = True
            out["speech"] = "Finally, press the other %s wheel into the axle. It should be the same size as the first wheel." % good_str
            out["video"] = video_url + "press_wheel_%s.mp4" % part_id
            return out

        wheels = self.get_objects_by_categories(img, {"%s_wheel_side" % good_str})

        if len(wheels) == 2:
            if self.frame_recs[0].add_and_check_stable(wheels[0]) and self.frame_recs[1].add_and_check_stable(wheels[1]):
                out["next"] = True
        else:
            self.frame_recs[0].staged_clear()

        return out

    def insert_brown_gear(self, img):
        out = defaultdict(lambda: None)
        if self.history["insert_brown_gear"] is False:
            self.clear_states()
            self.history["insert_brown_gear"] = True
            out["speech"] = "Place the brown gear as shown. Orient it such that the part that sticks out is facing in."
            out["video"] = video_url + "brown_gear.mp4"
            return out

        bad_brown = self.get_objects_by_categories(img, {"brown_gear_bad"})
        if len(bad_brown) >= 1:
            out["speech"] = "Make sure the gear is oriented correctly. The part that sticks out should be facing the inside of the frame."
            self.frame_recs[0].clear()
            self.delay_flag = True
            return out

        good_brown = self.get_objects_by_categories(img, {"brown_gear_good"})
        if len(good_brown) == 1:
            if self.frame_recs[0].add_and_check_stable(good_brown[0]) is True:
                out["next"] = True
        else:
            self.frame_recs[0].staged_clear()

        return out

    def insert_pink_gear_back(self, img):
        out = defaultdict(lambda: None)
        if self.history["insert_pink_gear_back"] is False:
            self.clear_states()
            self.history["insert_pink_gear_back"] = True
            out["speech"] = "Now, place the pink gear next to the brown gear as shown. The teeth should be facing out."
            out["video"] = video_url + "brown_gear.mp4"
            return out

        bad_pink = self.get_objects_by_categories(img, {"back_pink_gear_bad"})
        if len(bad_pink) >= 1:
            out["speech"] = "Make sure the gear is oriented correctly. The teeth should be facing out."
            self.frame_recs[0].clear()
            self.delay_flag = True
            return out

        good_pink = self.get_objects_by_categories(img, {"back_pink_gear_good"})
        if len(good_pink) == 1:
            if self.frame_recs[0].add_and_check_stable(good_pink[0]) is True:
                out["next"] = True
        else:
            self.frame_recs[0].staged_clear()

        return out

    def add_gear_axle(self, img):
        out = defaultdict(lambda: None)
        if self.history["add_gear_axle"] is False:
            self.clear_states()
            self.history["add_gear_axle"] = True
            out["speech"] = "Finally, find the gear axle. Use it to connect the two gear systems together."
            out["video"] = video_url + "add_gear_axle.mp4"
            return out

        gear_on_axle = self.get_objects_by_categories(img, {"gear_on_axle"})
        front_pink_gear = self.get_objects_by_categories(img, {"front_gear_good"})
        back_pink_gear = self.get_objects_by_categories(img, {"back_pink_gear_good"})
        back_brown_gear = self.get_objects_by_categories(img, {"back_brown_gear_good"})

        if len(gear_on_axle) == 2 and len(front_pink_gear) == 1 and len(back_pink_gear) == 1 and len(back_brown_gear) == 1:
            left, right = separate_two(gear_on_axle, True)
            if self.frame_recs[0].add_and_check_stable(left) and self.frame_recs[1].add_and_check_stable(right):
                left_box = self.frame_recs[0].averaged_bbox()
                right_box = self.frame_recs[1].averaged_bbox()

                if check_gear_axle_front(left_box, front_pink_gear["dimensions"]) is False:
                    pass
                elif check_gear_axle_back(left_box, back_pink_gear["dimensions"], back_brown_gear["dimensions"]) is False:
                    pass
                else:
                    out["next"] = True
        else:
            self.all_staged_clear()

        return out

    def final_check(self, img):
        # TODO
        out = defaultdict(lambda: None)
        if self.history["final_check"] is False:
            self.clear_states()
            self.history["final_check"] = True
            out["speech"] = "Please show me what you have, like this."
            out["image"] = read_image("final_check.jpg")
            return out

        wheels = self.get_objects_by_categories(img, {"thin_wheel_side", "thick_wheel_side"})

        if len(wheels) == 2:
            top, bottom = separate_two(wheels, False)
            top_check = self.frame_recs[0].add_and_check_stable(top)
            bottom_check = self.frame_recs[1].add_and_check_stable(bottom)

            if top_check is True and bottom_check is True:
                var = compare(self.frame_recs[0].averaged_bbox(), self.frame_recs[1].averaged_bbox(), wheel_compare_threshold)
                if var == "same":
                    out["next"] = True
        else:
            self.frame_recs[0].staged_clear()
            self.frame_recs[1].staged_clear()

        return out

    def complete(self):
        out = defaultdict(lambda: None)
        if self.history["complete"] is False:
            self.history["complete"] = True
            out["speech"] = "Great job! We've finished assembling the wheels and gear train!"
            out["next"] = True

        return out

    def clear_states(self):
        for rec in self.frame_recs.values():
            rec.clear()

    def all_staged_clear(self):
        for rec in self.frame_recs.values():
            rec.staged_clear()

def check_gear_axle_front(gear_on_axle_box, front_pink_gear_box):
    pass

def check_gear_axle_back(gear_on_axle_box, back_pink_gear_box, back_brown_gear_box):
    pass

def separate_two(objects, left_right=True):
    obj1 = objects[0]
    obj2 = objects[1]

    dim = 0 if left_right is True else 1  # left-right vs top-bottom

    if obj1["dimensions"][dim] < obj2["dimensions"][dim]:
        one = obj1
        two = obj2
    else:
        one = obj2
        two = obj1

    return one, two

def bbox_center(dims):
    return dims[2] - dims[0], dims[3] - dims[1]

def bbox_height(dims):
    return dims[3] - dims[1]

def bbox_diff(box1, box2):
    center1 = bbox_center(box1)
    center2 = bbox_center(box2)

    x_diff = abs(center1[0] - center2[0])
    y_diff = abs(center1[1] - center2[1])

    return math.sqrt(x_diff**2 + y_diff**2)

def compare(box1, box2, threshold):
    height1 = bbox_height(box1)
    height2 = bbox_height(box2)

    diff = abs(height1 - height2)
    if diff < threshold:
        return "same"

    return "first" if height1 > height2 else "second"

def read_image(name):
    image_path = os.path.join(resources, name)
    return cv2.imread(image_path)

def get_orientation(side_marker, horn):
    side = "left" if side_marker["class_name"] == "frame_marker_left" else "right"

    left_obj, right_obj = separate_two([side_marker, horn], True)
    if side == "left":
        flipped = left_obj["class_name"] == "frame_horn"
    else:
        flipped = right_obj["class_name"] == "frame_horn"

    return side, flipped

