package dfsha;

import com.google.protobuf.ByteString;
import io.grpc.Metadata;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.netty.shaded.io.grpc.netty.GrpcSslContexts;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.stub.StreamObserver;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Nodo de almacenamiento P2P. Los pares se vigilan y actualizan entre sí por gRPC. */
public final class NodeServer {
    private NodeServer() {}

    public static void main(String[] args) throws Exception {
        NodeConfig config = NodeConfig.fromEnvironment();
        BlockNode service = new BlockNode(config);
        NettyServerBuilder builder = NettyServerBuilder.forPort(config.port).maxInboundMessageSize(config.maxMessageBytes).addService(service)
                .intercept(new TokenInterceptor(config.token));
        if (config.cert != null) builder.sslContext(GrpcSslContexts.forServer(config.cert.toFile(), config.key.toFile()).build());
        Server server = builder.build().start();
        service.start();
        Runtime.getRuntime().addShutdownHook(new Thread(() -> { service.close(); server.shutdown(); }));
        System.out.println("Nodo Java P2P activo en " + config.nodeId);
        server.awaitTermination();
    }

    static final class NodeConfig {
        final String nodeId, token, authority;
        final int port, maxMessageBytes;
        final Path storage, cert, key, ca;
        final List<String> peers;
        NodeConfig(String nodeId, int port, int maxMessageBytes, String token, Path storage, Path cert, Path key, Path ca, String authority, List<String> peers) {
            this.nodeId=nodeId; this.port=port; this.maxMessageBytes=maxMessageBytes; this.token=token; this.storage=storage; this.cert=cert; this.key=key; this.ca=ca; this.authority=authority; this.peers=peers;
        }
        static NodeConfig fromEnvironment() {
            Map<String,String> e=System.getenv();
            int port=Integer.parseInt(e.getOrDefault("DFS_NODE_PORT","50051"));
            String id=e.getOrDefault("DFS_NODE_ID","localhost:"+port);
            List<String> peers=new ArrayList<>();
            for(String value:e.getOrDefault("DFS_NODES",id).split(",")) if(!value.isBlank()) peers.add(value.trim());
            String cert=e.get("DFS_NODE_TLS_CERT"), key=e.get("DFS_NODE_TLS_KEY"), ca=e.get("DFS_NODE_TLS_CA");
            if ((cert==null)!=(key==null)) throw new IllegalArgumentException("El certificado y la llave TLS deben configurarse juntos");
            if (e.getOrDefault("DFS_STORAGE_KEY","").isBlank()) throw new IllegalArgumentException("DFS_STORAGE_KEY es obligatorio");
            int maxMessageBytes=Integer.parseInt(e.getOrDefault("DFS_GRPC_MAX_MESSAGE_BYTES", "68157440"));
            return new NodeConfig(id,port,maxMessageBytes,e.getOrDefault("DFS_NODE_TOKEN",""),Path.of(e.getOrDefault("DFS_NODE_STORAGE","/var/lib/dfsha")), cert==null?null:Path.of(cert), key==null?null:Path.of(key), ca==null?null:Path.of(ca), e.getOrDefault("DFS_NODE_TLS_SERVER_NAME",""),peers);
        }
    }

    static final class TokenInterceptor implements ServerInterceptor {
        private static final Metadata.Key<String> AUTH=Metadata.Key.of("authorization",Metadata.ASCII_STRING_MARSHALLER);
        final String token;
        TokenInterceptor(String token){this.token=token;}
        public <ReqT,RespT> ServerCall.Listener<ReqT> interceptCall(ServerCall<ReqT,RespT> call, Metadata headers, ServerCallHandler<ReqT,RespT> next) {
            if (!token.isBlank() && !("Bearer "+token).equals(headers.get(AUTH))) { call.close(io.grpc.Status.UNAUTHENTICATED.withDescription("Token interno inválido"),new Metadata()); return new ServerCall.Listener<>(){}; }
            return next.startCall(call,headers);
        }
    }

    static final class BlockNode extends BloqueServicioGrpc.BloqueServicioImplBase implements AutoCloseable {
        final NodeConfig config; final EncryptedStorage storage; final Map<String,NodoMembresia> members=new ConcurrentHashMap<>(); final Map<String,Peer> peers=new ConcurrentHashMap<>(); final java.util.concurrent.ScheduledExecutorService monitor=java.util.concurrent.Executors.newSingleThreadScheduledExecutor();
        BlockNode(NodeConfig config) throws Exception { this.config=config; this.storage=new EncryptedStorage(config.storage,System.getenv("DFS_STORAGE_KEY")); for(String peer:config.peers) members.put(peer, member(peer,"activo")); }
        void start(){ monitor.scheduleWithFixedDelay(this::heartbeatPeers,0,5,TimeUnit.SECONDS); }
        NodoMembresia member(String address,String state){ int separator=address.lastIndexOf(":"); int port=Integer.parseInt(address.substring(separator + 1)); return NodoMembresia.newBuilder().setNodeId(address).setDireccion(address).setPuerto(port).setEstado(state).setHashPosition(Hashing.sha256(address).toString(16)).setLastHeartbeat(Instant.now().toString()).setCapacidadDisponibleBytes(config.storage.toFile().getUsableSpace()).build(); }
        @Override public void heartbeat(HeartbeatRequest request, StreamObserver<HeartbeatResponse> out){ out.onNext(HeartbeatResponse.newBuilder().setExito(true).setNodeId(config.nodeId).setEstado("activo").setLastHeartbeatUnixMs(System.currentTimeMillis()).setCapacidadDisponibleBytes(config.storage.toFile().getUsableSpace()).build()); out.onCompleted(); }
        @Override public void actualizarMembresia(ActualizarMembresiaRequest request, StreamObserver<ActualizarMembresiaResponse> out){ for(NodoMembresia node:request.getNodosList()) members.put(node.getDireccion(),node); out.onNext(ActualizarMembresiaResponse.newBuilder().setExito(true).setMiembros(members.size()).build()); out.onCompleted(); }
        @Override public void escribirBloque(EscribirBloqueRequest request, StreamObserver<EscribirBloqueResponse> out){ try { storage.save(request); out.onNext(EscribirBloqueResponse.newBuilder().setExito(true).setMensaje("Bloque guardado correctamente").setBlockId(request.getBlockId()).build()); } catch(Exception e){out.onNext(EscribirBloqueResponse.newBuilder().setExito(false).setMensaje(e.getMessage()).setBlockId(request.getBlockId()).build());} out.onCompleted(); }
        @Override public void replicarBloque(ReplicarBloqueRequest request, StreamObserver<ReplicarBloqueResponse> out){ int confirmed=0; List<String> errors=new ArrayList<>(); try { storage.save(request); confirmed++; } catch(Exception e){ out.onNext(ReplicarBloqueResponse.newBuilder().setExito(false).setMensaje(e.getMessage()).build());out.onCompleted();return; } for(String dest:request.getDestinosList().stream().distinct().toList()) { if(dest.equals(config.nodeId) || !active(dest)){errors.add(dest+": destino fuera de membresía activa");continue;} try { EscribirBloqueResponse r=peer(dest).write(request); if(r.getExito())confirmed++;else errors.add(dest+": "+r.getMensaje()); } catch(Exception e){ errors.add(dest+": no disponible"); } } out.onNext(ReplicarBloqueResponse.newBuilder().setExito(true).setReplicasConfirmadas(confirmed).setMensaje("Bloque guardado en "+confirmed+" nodo(s)"+(errors.isEmpty()?"":"; "+String.join("; ",errors))).build());out.onCompleted(); }
        @Override public void leerBloque(LeerBloqueRequest request, StreamObserver<LeerBloqueResponse> out){ try { StoredBlock b=storage.load(request.getBlockId()); if(b==null) out.onNext(LeerBloqueResponse.newBuilder().setExito(false).setMensaje("Bloque no encontrado").setBlockId(request.getBlockId()).build()); else out.onNext(LeerBloqueResponse.newBuilder().setExito(true).setMensaje("Bloque leído correctamente").setBlockId(request.getBlockId()).setFileId(b.fileId).setPosicion(b.position).setContenido(ByteString.copyFrom(b.content)).setChecksum(b.checksum).build()); } catch(Exception e){out.onNext(LeerBloqueResponse.newBuilder().setExito(false).setMensaje(e.getMessage()).setBlockId(request.getBlockId()).build());} out.onCompleted(); }
        @Override public void eliminarBloque(EliminarBloqueRequest request, StreamObserver<EliminarBloqueResponse> out){ boolean ok=storage.delete(request.getBlockId());out.onNext(EliminarBloqueResponse.newBuilder().setExito(ok).setMensaje(ok?"Bloque eliminado correctamente":"Bloque no encontrado").build());out.onCompleted(); }
        boolean active(String address){ NodoMembresia node=members.get(address);return node!=null&&"activo".equals(node.getEstado()); }
        Peer peer(String address) throws Exception { Peer current=peers.get(address);if(current!=null)return current;Peer made=new Peer(address,config);peers.put(address,made);return made; }
        void heartbeatPeers(){ boolean changed=false; for(String address:new ArrayList<>(members.keySet())) if(!address.equals(config.nodeId)){ try { peer(address).heartbeat(); NodoMembresia before=members.get(address);if(before==null||!"activo".equals(before.getEstado()))changed=true;members.put(address,member(address,"activo")); }catch(Exception e){NodoMembresia before=members.get(address);if(before!=null&&"activo".equals(before.getEstado())){changed=true;System.err.println("Heartbeat P2P falló hacia "+address+": "+e.getMessage());}members.put(address,member(address,"no_disponible"));} } if(changed) broadcast(); }
        void broadcast(){ List<NodoMembresia> view=new ArrayList<>(members.values()); for(String address:new ArrayList<>(members.keySet())) if(!address.equals(config.nodeId)&&active(address)) try{peer(address).membership(view);}catch(Exception ignored){} }
        public void close(){monitor.shutdownNow();peers.values().forEach(Peer::close);}
    }

    static final class Peer implements AutoCloseable { final io.grpc.ManagedChannel channel; final BloqueServicioGrpc.BloqueServicioBlockingStub stub; final Metadata metadata=new Metadata(); static final Metadata.Key<String> AUTH=Metadata.Key.of("authorization",Metadata.ASCII_STRING_MARSHALLER); Peer(String address,NodeConfig c) throws Exception { NettyChannelBuilder b=NettyChannelBuilder.forTarget(address).maxInboundMessageSize(c.maxMessageBytes); if(c.ca!=null){var ssl=GrpcSslContexts.forClient().trustManager(c.ca.toFile()).build();b.sslContext(ssl);if(!c.authority.isBlank())b.overrideAuthority(c.authority);}else b.usePlaintext(); channel=b.build();if(!c.token.isBlank())metadata.put(AUTH,"Bearer "+c.token);stub=BloqueServicioGrpc.newBlockingStub(channel).withInterceptors(io.grpc.stub.MetadataUtils.newAttachHeadersInterceptor(metadata)); } EscribirBloqueResponse write(ReplicarBloqueRequest r){return stub.withDeadlineAfter(10,TimeUnit.SECONDS).escribirBloque(EscribirBloqueRequest.newBuilder().setBlockId(r.getBlockId()).setFileId(r.getFileId()).setPosicion(r.getPosicion()).setContenido(r.getContenido()).setChecksum(r.getChecksum()).build());} void heartbeat(){stub.withDeadlineAfter(3,TimeUnit.SECONDS).heartbeat(HeartbeatRequest.newBuilder().setRequesterId("peer").build());} void membership(Collection<NodoMembresia> nodes){stub.withDeadlineAfter(5,TimeUnit.SECONDS).actualizarMembresia(ActualizarMembresiaRequest.newBuilder().addAllNodos(nodes).build());} public void close(){channel.shutdownNow();} }

    record StoredBlock(byte[] content,String checksum,String fileId,int position) {}
    static final class EncryptedStorage { final Path dir; final SecretKey key; EncryptedStorage(Path dir,String raw) throws Exception {this.dir=dir;Files.createDirectories(dir);byte[] k=decodeKey(raw);if(k.length!=32)throw new IllegalArgumentException("DFS_STORAGE_KEY debe contener 32 bytes");key=new SecretKeySpec(k,"AES");} void save(EscribirBloqueRequest r)throws Exception{save(r.getBlockId(),r.getFileId(),r.getPosicion(),r.getContenido().toByteArray(),r.getChecksum());} void save(ReplicarBloqueRequest r)throws Exception{save(r.getBlockId(),r.getFileId(),r.getPosicion(),r.getContenido().toByteArray(),r.getChecksum());} void save(String id,String file,int position,byte[] data,String checksum)throws Exception{valid(id);String actual=hex(MessageDigest.getInstance("SHA-256").digest(data));if(!checksum.isBlank()&&!checksum.equals(actual))throw new IllegalArgumentException("El checksum no coincide");String metadata=metadata(file,position,data.length,actual); byte[] nonce=new byte[12];new java.security.SecureRandom().nextBytes(nonce);Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key,new GCMParameterSpec(128,nonce));cipher.updateAAD((metadata+id).getBytes(StandardCharsets.UTF_8));byte[] encrypted=cipher.doFinal(data); byte[] disk=concat("DFSAESG1".getBytes(StandardCharsets.US_ASCII),nonce,encrypted); Path binTemp=dir.resolve("."+id+".bin.tmp"), metaTemp=dir.resolve("."+id+".json.tmp"); Files.write(binTemp,disk); Files.writeString(metaTemp,metadata,StandardCharsets.UTF_8); Files.move(binTemp,dir.resolve(id+".bin"),java.nio.file.StandardCopyOption.REPLACE_EXISTING,java.nio.file.StandardCopyOption.ATOMIC_MOVE); Files.move(metaTemp,dir.resolve(id+".json"),java.nio.file.StandardCopyOption.REPLACE_EXISTING,java.nio.file.StandardCopyOption.ATOMIC_MOVE);} StoredBlock load(String id)throws Exception{valid(id);Path binary=dir.resolve(id+".bin"),meta=dir.resolve(id+".json");if(!Files.exists(binary)||!Files.exists(meta))return null;byte[] value=Files.readAllBytes(binary);if(value.length<20)throw new IOException("Bloque inválido");String metadata=Files.readString(meta,StandardCharsets.UTF_8); byte[] nonce=java.util.Arrays.copyOfRange(value,8,20);Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key,new GCMParameterSpec(128,nonce));cipher.updateAAD((metadata+id).getBytes(StandardCharsets.UTF_8));byte[] data=cipher.doFinal(java.util.Arrays.copyOfRange(value,20,value.length)); String checksum=hex(MessageDigest.getInstance("SHA-256").digest(data)); if(!checksum.equals(field(metadata,"checksum")))throw new IOException("Checksum inválido"); return new StoredBlock(data,checksum,field(metadata,"file_id"),Integer.parseInt(field(metadata,"posicion")));} boolean delete(String id){try{valid(id);return Files.deleteIfExists(dir.resolve(id+".bin"))&&Files.deleteIfExists(dir.resolve(id+".json"));}catch(Exception e){return false;}} static String metadata(String file,int position,int size,String checksum){return "{\"checksum\":\""+checksum+"\",\"file_id\":\""+file+"\",\"posicion\":"+position+",\"tamano\":"+size+"}";} static String field(String json,String name){java.util.regex.Matcher m=java.util.regex.Pattern.compile("\\\""+name+"\\\"\\s*:\\s*(?:\\\"([^\\\"]*)\\\"|([0-9]+))").matcher(json);if(!m.find())throw new IllegalArgumentException("Metadato inválido");return m.group(1)!=null?m.group(1):m.group(2);} static byte[] decodeKey(String raw) { try { return Base64.getUrlDecoder().decode(raw); } catch (IllegalArgumentException ignored) { return Base64.getDecoder().decode(raw); } } static void valid(String id){if(!id.matches("[A-Za-z0-9._-]{1,200}"))throw new IllegalArgumentException("Identificador de bloque inválido");} static String hex(byte[] v){return java.util.HexFormat.of().formatHex(v);} static byte[] concat(byte[]...a){int n=0;for(byte[]x:a)n+=x.length;byte[]r=new byte[n];int p=0;for(byte[]x:a){System.arraycopy(x,0,r,p,x.length);p+=x.length;}return r;} }
}
