// VITE_* settings are public build-time configuration. Never put a secret here.
const base=(import.meta.env?.VITE_API_BASE_URL||'').replace(/[/]+$/,'');
if(base){const url=new URL(base);if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(url.hostname)))throw new Error('VITE_API_BASE_URL must use HTTPS (localhost is allowed for development).');if(url.pathname!=='/'||url.search||url.hash||url.username||url.password)throw new Error('VITE_API_BASE_URL must be an origin, without a path or credentials.');}
export const serverOcrEnabled=import.meta.env?.VITE_ENABLE_SERVER_OCR==='true';
export const passwordRequired=import.meta.env?.VITE_REQUIRE_ACCESS_PASSWORD==='true';
let accessToken='';
export function setAccessToken(token:string){accessToken=token;}
export function apiUrl(path:string){if(!path.startsWith('/api/'))throw new Error('Invalid API path');return `${base}${path}`;}
export function apiHeaders(headers?:HeadersInit){const result=new Headers(headers);if(accessToken)result.set('Authorization',`Bearer ${accessToken}`);return result;}
export function apiFetch(path:string,options:RequestInit={}){return fetch(apiUrl(path),{...options,headers:apiHeaders(options.headers),credentials:'omit'});}
