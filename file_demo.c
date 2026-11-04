/* C file-handling demonstration for the project */
#include <stdio.h>

int main(void) {
    FILE *fp;
    char text[200];

    fp = fopen("c_demo.txt", "w");
    if (fp == NULL) {
        printf("Unable to create file.\\n");
        return 1;
    }
    fprintf(fp, "File and Folder Management System - C demo\\n");
    fclose(fp);

    fp = fopen("c_demo.txt", "r");
    if (fp == NULL) {
        printf("Unable to open file.\\n");
        return 1;
    }
    while (fgets(text, sizeof(text), fp) != NULL) {
        printf("%s", text);
    }
    fclose(fp);
    return 0;
}
