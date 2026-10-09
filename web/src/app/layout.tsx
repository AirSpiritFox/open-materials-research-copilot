import type { Metadata, Viewport } from "next";
import "./globals.css";
const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
export const metadata: Metadata = {title:"Open Materials Research Copilot",description:"Open literature, traceable sources, and a research notebook that goes with you.",manifest:base+"/manifest.webmanifest",icons:{icon:base+"/icon.svg",apple:base+"/icon-192.png"},appleWebApp:{capable:true,statusBarStyle:"default",title:"Open Materials"}};
export const viewport: Viewport = {width:"device-width",initialScale:1,themeColor:"#112a3a"};
export default function Layout({children}:{children:React.ReactNode}) {return <html lang="en"><body>{children}</body></html>;}
