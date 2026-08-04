package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp44 address-structured: Change the address to a structured form: the request now provides 'addressLine1', an optio... */
@Tag("cp44")
class Cp44Tests extends AcceptanceBase {

	@Test
	void coreAcceptsStructuredAddress() throws Exception {
		ObjectNode o = structuredOwner();
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.addressLine1").exists())
				.andExpect(jsonPath("$.address").exists()); // composed string
	}
}
