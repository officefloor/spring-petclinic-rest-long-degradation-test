package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** telephone-unique: — duplicate telephones are compared as E.164. */
@Tag("cp03")
class Cp03Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateAcrossFormats() throws Exception {
		// national and international forms of the same number must collide
		ObjectNode a = ownerNode(); a.put("telephone", "0412 345 678");
		createOwnerOk(a);
		ObjectNode b = ownerNode(); b.put("telephone", "+61 412 345 678");
		createOwner(b).andExpect(status().isConflict());
	}
}
