FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY Cluster/pom.xml ./pom.xml
COPY Proto /Proto
COPY Cluster/src ./src
RUN mvn --batch-mode package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/target/dfsha-cluster-1.0.jar ./cluster.jar
EXPOSE 8081
CMD ["java", "-jar", "cluster.jar"]
