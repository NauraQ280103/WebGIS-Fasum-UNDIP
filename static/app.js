function initMap(reports){
  const map = L.map('map', {zoomControl:false}).setView([-7.05,110.44], 15);
  L.control.zoom({position:'bottomright'}).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(map);
  const markers=[];
  reports.forEach(r=>{
    const marker=L.marker([r.lat,r.lon]).addTo(map);
    marker.bindPopup(`<div class="popup"><span class="badge approved">Approved</span><h3>${escapeHtml(r.title)}</h3><p><b>${escapeHtml(r.category)}</b> · ${escapeHtml(r.damage)}</p><p>${escapeHtml(r.description)}</p><small>${r.date}</small><br><a href="/report/${r.id}">Lihat detail →</a></div>`);
    marker._report=r; markers.push(marker);
  });
  function filter(){
    const q=(document.getElementById('mapSearch').value||'').toLowerCase();
    const c=document.getElementById('categoryFilter').value;
    markers.forEach(m=>{
      const r=m._report; const ok=(!q || (r.title+r.category+r.damage+r.description).toLowerCase().includes(q)) && (!c || r.category===c);
      if(ok) m.addTo(map); else map.removeLayer(m);
    });
  }
  document.getElementById('mapSearch').addEventListener('input',filter);
  document.getElementById('categoryFilter').addEventListener('change',filter);
}
function initReportForm(data){
  const category=document.getElementById('category'), damage=document.getElementById('damage_type');
  category.addEventListener('change',()=>{
    damage.innerHTML='<option value="">Pilih jenis kerusakan</option>';
    (data[category.value]||[]).forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;damage.appendChild(o)});
  });
  const map=L.map('pickMap').setView([-7.05,110.44],15);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(map);
  let marker;
  function setPoint(lat,lon){
    document.getElementById('latitude').value=lat.toFixed(7); document.getElementById('longitude').value=lon.toFixed(7);
    document.getElementById('locationStatus').textContent=`Lokasi dipilih: ${lat.toFixed(6)}, ${lon.toFixed(6)}`;
    if(marker) marker.setLatLng([lat,lon]); else marker=L.marker([lat,lon],{draggable:true}).addTo(map);
    marker.on('dragend',()=>{const p=marker.getLatLng();setPoint(p.lat,p.lng)});
  }
  map.on('click',e=>setPoint(e.latlng.lat,e.latlng.lng));
  document.getElementById('extractGps').addEventListener('click',async()=>{
    const f=document.getElementById('photo').files[0]; if(!f){alert('Pilih foto terlebih dahulu.');return}
    const fd=new FormData();fd.append('photo',f);
    const res=await fetch('/report/extract-gps',{method:'POST',body:fd}); const data=await res.json();
    if(data.ok){setPoint(data.latitude,data.longitude);map.setView([data.latitude,data.longitude],18);document.getElementById('locationStatus').textContent='Koordinat berhasil dibaca dari EXIF foto.'}
    else document.getElementById('locationStatus').textContent=data.message+' Silakan titikkan lokasi di peta.';
  });
}
function initDetailMap(lat,lon,title){
  const map=L.map('detailMap').setView([lat,lon],18);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'© OpenStreetMap'}).addTo(map);
  L.marker([lat,lon]).addTo(map).bindPopup(escapeHtml(title)).openPopup();
}
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
