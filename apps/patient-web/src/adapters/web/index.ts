import type { PlatformAdapters } from "../types";
import { webStorageAdapter } from "./StorageAdapter";
import { webAudioAdapter } from "./AudioAdapter";
import { webNotificationAdapter } from "./NotificationAdapter";
import { webCameraAdapter } from "./CameraAdapter";
import { webMicAdapter } from "./MicAdapter";
import { webFileAdapter } from "./FileAdapter";

export const webAdapters: PlatformAdapters = {
  storage: webStorageAdapter,
  audio: webAudioAdapter,
  notification: webNotificationAdapter,
  camera: webCameraAdapter,
  mic: webMicAdapter,
  file: webFileAdapter
};

export { db } from "./db";
