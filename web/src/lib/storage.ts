import type {Project} from "./types";
export type {Project} from "./types";
const DATABASE="open-materials-research-copilot",VERSION=1,STORE="projects";
let databasePromise:Promise<IDBDatabase>|undefined;
export function newProject(name:string,question=""):Project{
 const cleaned=name.trim();if(!cleaned||cleaned.length>160)throw new Error("Project names must contain 1–160 characters.");
 return {id:crypto.randomUUID(),name:cleaned,question:question.trim().slice(0,12000),notes:"",papers:[],searches:[],created_at:new Date().toISOString()};
}
function database():Promise<IDBDatabase>{
 if(typeof indexedDB==="undefined")return Promise.reject(new Error("Local storage is unavailable in this browser. Project changes cannot be saved."));
 if(databasePromise)return databasePromise;
 databasePromise=new Promise((resolve,reject)=>{
  const request=indexedDB.open(DATABASE,VERSION);
  request.onupgradeneeded=event=>{
   const db=request.result;if(!db.objectStoreNames.contains(STORE))db.createObjectStore(STORE,{keyPath:"id"});
   if(event.oldVersion===0){const example:Project={id:"sample-tellurite",name:"Tellurite optical research",question:"Investigate tellurite-based glasses for optical or volumetric-display applications. Identify compositions studied experimentally, dopants, synthesis routes, optical properties, thermal stability and major limitations. Compare the strongest candidates and identify what still requires experimental validation.",notes:"Starting research question only. No papers, measurements, or scientific conclusions have been prefilled. Search open literature to build your own source collection.",papers:[],searches:[],created_at:new Date().toISOString()};request.transaction!.objectStore(STORE).add(example);}
  };
  request.onerror=()=>reject(new Error("The project database could not open: "+(request.error?.message||"browser storage error")));
  request.onblocked=()=>reject(new Error("Close other app tabs and reopen this page to upgrade the project database."));
  request.onsuccess=()=>{const db=request.result;db.onversionchange=()=>{db.close();databasePromise=undefined;};resolve(db);};
 });
 databasePromise.catch(()=>{databasePromise=undefined;});return databasePromise;
}
async function transaction<T>(mode:IDBTransactionMode,run:(store:IDBObjectStore)=>IDBRequest<T>):Promise<T>{
 const db=await database();return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,mode),request=run(tx.objectStore(STORE));let value:T;
 request.onsuccess=()=>{value=request.result;};tx.oncomplete=()=>resolve(value);
 tx.onerror=()=>reject(new Error("Project data could not be "+(mode==="readonly"?"read":"saved")+": "+(tx.error?.message||request.error?.message||"storage unavailable")));
 tx.onabort=()=>reject(new Error("Project changes were not saved. Storage may be full or blocked by browser settings."));
 });
}
export async function listProjects():Promise<Project[]>{const values=await transaction<Project[]>("readonly",store=>store.getAll());return values.sort((a,b)=>b.created_at.localeCompare(a.created_at));}
export async function saveProject(project:Project):Promise<void>{
 if(!project.id||!project.name.trim()||project.name.length>160||!Array.isArray(project.papers)||!Array.isArray(project.searches))throw new Error("Invalid project data. Changes were not saved.");
 const serialized=JSON.stringify(project);if(serialized.length>30_000_000)throw new Error("This project exceeds the 30 MB local-project limit. Export it before starting a second project.");
 await transaction("readwrite",store=>store.put(JSON.parse(serialized) as Project));
}
export async function deleteProject(id:string):Promise<void>{if(!id)throw new Error("A project ID is required.");await transaction("readwrite",store=>store.delete(id));}
export async function requestPersistentStorage():Promise<boolean>{return typeof navigator!=="undefined"&&navigator.storage?.persist?navigator.storage.persist():false;}
