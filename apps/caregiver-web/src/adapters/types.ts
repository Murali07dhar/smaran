export interface StorageAdapter{get(k:string):string|null;set(k:string,v:string):void}
export interface FileAdapter{download(name:string,data:Blob):void}
export interface MicAdapter{record():Promise<{stop():Promise<{blob:Blob;mime:string}>}>}
export interface CameraAdapter{capture():Promise<Blob>}
export interface AudioAdapter{play(src:string):Promise<void>}
export interface NotificationAdapter{notify(title:string,body:string):Promise<void>}
