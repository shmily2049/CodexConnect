/* Uses libdmg-hfsplus to preserve and audit exact file modes and links. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <hfs/hfsplus.h>
#include <hfs/hfslib.h>
char endianness;
int main(int argc, char **argv) {
 if(argc!=5) return 2;
 short value=1; endianness=*((char*)&value)?IS_LITTLE_ENDIAN:IS_BIG_ENDIAN;
 io_func *io=openFlatFile(argv[2]); if(!io)return 3;
 Volume *vol=openVolume(io); if(!vol)return 4;
 FILE *list=fopen(argv[4],"r"); if(!list)return 5;
 int pack=strcmp(argv[1],"pack")==0; char *line=NULL; size_t cap=0; int count=0;
 while(getline(&line,&cap,list)>0) {
  line[strcspn(line,"\r\n")]=0;
  char *kind=strtok(line,"\t"),*mode=strtok(NULL,"\t"),*rel=strtok(NULL,"\t"),*target=strtok(NULL,"\t");
  if(!kind||!mode||!rel||!target)return 6;
  unsigned bits=strtoul(mode,NULL,8); char path[2048],local[4096];
  if(snprintf(path,sizeof(path),"/%s",rel)>=(int)sizeof(path))return 7;
  if(snprintf(local,sizeof(local),"%s/%s",argv[3],rel)>=(int)sizeof(local))return 8;
  if(pack) {
   if(*kind=='D') { if(!newFolder(path,vol))return 9; }
   else if(*kind=='L') { makeSymlink(path,target,vol); }
   else { FILE *f=fopen(local,"rb"); if(!f)return 10; if(!add_hfs(vol,createAbstractFileFromFile(f),path))return 11; }
  }
  HFSPlusCatalogRecord *rec=getRecordFromPath3(path,vol,NULL,NULL,FALSE,FALSE,kHFSRootFolderID);
  if(!rec){fprintf(stderr,"Missing: %s\n",path);return 12;}
  HFSPlusBSDInfo *perms=rec->recordType==kHFSPlusFolderRecord?&((HFSPlusCatalogFolder*)rec)->permissions:&((HFSPlusCatalogFile*)rec)->permissions;
  if(pack){perms->fileMode=bits; updateCatalog(vol,rec);}
  else {
   if(perms->fileMode!=bits){fprintf(stderr,"Mode: %s %o != %o\n",path,perms->fileMode,bits);return 13;}
   if(*kind!='D') { FILE *f=fopen(local,"wb"); if(!f)return 14; AbstractFile *out=createAbstractFileFromFile(f); writeToFile((HFSPlusCatalogFile*)rec,out,vol);out->close(out); }
  }
  free(rec); count++;
 }
 free(line);fclose(list);closeVolume(vol);CLOSE(io);printf("Checked %d entries\n",count);return 0;
}
