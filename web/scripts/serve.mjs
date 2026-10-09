import http from "node:http";
import {readFile,stat} from "node:fs/promises";
import {resolve,extname,sep} from "node:path";
const root=resolve("out"),base=process.env.NEXT_PUBLIC_BASE_PATH||"";
const mime={".html":"text/html",".js":"application/javascript",".css":"text/css",".json":"application/json",".webmanifest":"application/manifest+json",".svg":"image/svg+xml",".png":"image/png",".txt":"text/plain",".woff2":"font/woff2"};
http.createServer(async(req,res)=>{try{const url=new URL(req.url,"http://localhost"),p=decodeURIComponent(url.pathname);if(!p.startsWith(base+"/")&&p!==base){res.writeHead(404);res.end();return;}const relative=p.slice(base.length),full=resolve(root,"."+relative);if(full!==root&&!full.startsWith(root+sep)){res.writeHead(403);res.end();return;}const file=(await stat(full)).isDirectory()?full+"/index.html":full;res.setHeader("Content-Type",mime[extname(file)]||"application/octet-stream");res.setHeader("Cache-Control","no-cache");res.end(await readFile(file));}catch{res.writeHead(404);res.end("Not found");}}).listen(4173,"0.0.0.0",()=>console.log("Preview: http://localhost:4173"+base+"/"));
