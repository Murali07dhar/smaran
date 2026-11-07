// Platform adapter interfaces used by this package. Web impls live in ./web; React Native supplies its own.
// (StorageAdapter, NotificationAdapter, CameraAdapter, MicAdapter, FileAdapter are owned by the host apps; this package only needs audio.)
export interface AudioAdapter { play(uri: string): Promise<void>; stop(): void }
